import { useState } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, Share,
} from 'react-native'
import { Picker } from '@react-native-picker/picker'
import { redactionAPI } from '../../src/api/client'

const PAYS = ['CM', 'SN', 'CI', 'TG', 'BJ']
const PAYS_LABELS: Record<string, string> = {
  CM: '🇨🇲 Cameroun', SN: '🇸🇳 Sénégal', CI: '🇨🇮 Côte d\'Ivoire', TG: '🇹🇬 Togo', BJ: '🇧🇯 Bénin',
}

const TYPES_COURANTS = [
  { cle: 'lettre_administrative', label: 'Lettre administrative' },
  { cle: 'demande_emploi', label: 'Demande d\'emploi' },
  { cle: 'cv', label: 'CV' },
  { cle: 'contrat_travail', label: 'Contrat de travail' },
  { cle: 'rapport_stage', label: 'Rapport de stage' },
  { cle: 'pv_reunion', label: 'PV de réunion' },
  { cle: 'devis_commercial', label: 'Devis commercial' },
  { cle: 'attestation_travail', label: 'Attestation de travail' },
  { cle: 'procuration', label: 'Procuration' },
  { cle: 'note_service', label: 'Note de service' },
]

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

export default function RedactionScreen() {
  const [typeDoc, setTypeDoc] = useState('lettre_administrative')
  const [pays, setPays] = useState('CM')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{ contenu_markdown: string; prix_fcfa: number; titre: string } | null>(null)

  const generer = async () => {
    if (!description.trim()) { Alert.alert('Erreur', 'Décrivez votre document'); return }
    setLoading(true)
    try {
      const r = await redactionAPI.generer({
        type_doc: typeDoc,
        informations: { description },
        pays,
      })
      setResultat(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert('Erreur', err.response?.data?.detail || 'Génération échouée')
    } finally {
      setLoading(false)
    }
  }

  const partager = async () => {
    if (!resultat) return
    await Share.share({
      message: resultat.contenu_markdown,
      title: resultat.titre,
    })
  }

  return (
    <ScrollView style={s.container} keyboardShouldPersistTaps="handled">
      <View style={s.header}>
        <Text style={s.title}>📝 Rédaction IA</Text>
        <Text style={s.subtitle}>Documents professionnels adaptés à l'Afrique</Text>
      </View>

      <View style={s.card}>
        {/* Type de document */}
        <Text style={s.label}>Type de document</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={typeDoc} onValueChange={setTypeDoc} style={s.picker}>
            {TYPES_COURANTS.map(t => (
              <Picker.Item key={t.cle} label={t.label} value={t.cle} />
            ))}
          </Picker>
        </View>

        {/* Pays */}
        <Text style={s.label}>Pays</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {PAYS.map(p => (
              <TouchableOpacity
                key={p}
                onPress={() => setPays(p)}
                style={[s.chip, pays === p && s.chipActive]}
              >
                <Text style={[s.chipText, pays === p && s.chipTextActive]}>{PAYS_LABELS[p]}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {/* Description */}
        <Text style={s.label}>Informations du document</Text>
        <TextInput
          style={s.textarea}
          value={description}
          onChangeText={setDescription}
          multiline
          numberOfLines={5}
          placeholder={`Destinataire : M. le Directeur\nObjet : demande de stage\nNom : Jean Dupont\nDate : 22 avril 2026`}
          placeholderTextColor="#9ca3af"
          textAlignVertical="top"
        />

        <TouchableOpacity
          style={[s.btn, loading && s.btnDisabled]}
          onPress={generer}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={s.btnText}>✨ Générer le document</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Résultat */}
      {resultat && (
        <View style={s.card}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={s.label}>{resultat.titre}</Text>
            <Text style={{ color: '#16a34a', fontWeight: '600', fontSize: 13 }}>{formatFCFA(resultat.prix_fcfa)}</Text>
          </View>
          <Text style={s.markdown}>{resultat.contenu_markdown}</Text>
          <TouchableOpacity style={[s.btn, { backgroundColor: '#16a34a', marginTop: 12 }]} onPress={partager}>
            <Text style={s.btnText}>📤 Partager</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  header: {
    backgroundColor: '#2563eb',
    paddingTop: 56,
    paddingBottom: 20,
    paddingHorizontal: 20,
  },
  title: { fontSize: 22, fontWeight: '700', color: '#fff' },
  subtitle: { fontSize: 13, color: '#bfdbfe', marginTop: 4 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 18,
    margin: 16,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 3,
  },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  pickerWrap: {
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    marginBottom: 16,
    overflow: 'hidden',
  },
  picker: { height: 48 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#f3f4f6',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  chipActive: { backgroundColor: '#2563eb', borderColor: '#2563eb' },
  chipText: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  chipTextActive: { color: '#fff' },
  textarea: {
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 13,
    color: '#111827',
    minHeight: 110,
    marginBottom: 16,
  },
  btn: {
    backgroundColor: '#2563eb',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  markdown: { fontSize: 13, color: '#374151', lineHeight: 20 },
})
