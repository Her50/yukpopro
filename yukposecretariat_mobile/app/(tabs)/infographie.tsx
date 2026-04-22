import { useState, useEffect } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, Share, Image,
} from 'react-native'
import { Picker } from '@react-native-picker/picker'
import { infographieAPI } from '../../src/api/client'

interface Gabarit {
  cle: string; label: string; width_mm: number; height_mm: number;
  categorie: string; prix_fcfa: number
}

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

export default function InfographieScreen() {
  const [gabarits, setGabarits] = useState<Gabarit[]>([])
  const [gabarit, setGabarit] = useState('flyer_a5')
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{ png_base64?: string; prix_fcfa: number; titre: string } | null>(null)

  useEffect(() => {
    infographieAPI.gabarits().then(r => {
      setGabarits(r.data.gabarits)
    }).catch(() => {})
  }, [])

  const generer = async () => {
    if (!brief.trim()) { Alert.alert('Erreur', 'Décrivez votre besoin'); return }
    setLoading(true)
    try {
      const r = await infographieAPI.generer({ brief, type_gabarit: gabarit, pays })
      setResultat(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert('Erreur', err.response?.data?.detail || 'Génération échouée')
    } finally {
      setLoading(false)
    }
  }

  const gabaritChoisi = gabarits.find(g => g.cle === gabarit)

  return (
    <ScrollView style={s.container} keyboardShouldPersistTaps="handled">
      <View style={s.header}>
        <Text style={s.title}>🎨 Infographie</Text>
        <Text style={s.subtitle}>Flyers, cartes, affiches print-ready</Text>
      </View>

      <View style={s.card}>
        {/* Gabarit */}
        <Text style={s.label}>Gabarit</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={gabarit} onValueChange={v => setGabarit(v)} style={s.picker}>
            {gabarits.map(g => (
              <Picker.Item
                key={g.cle}
                label={`${g.label} (${g.width_mm}×${g.height_mm}mm) — ${formatFCFA(g.prix_fcfa)}`}
                value={g.cle}
              />
            ))}
          </Picker>
        </View>
        {gabaritChoisi && (
          <Text style={{ fontSize: 11, color: '#9ca3af', marginBottom: 12 }}>
            {gabaritChoisi.width_mm}mm × {gabaritChoisi.height_mm}mm · Bleed inclus · PDF print-ready
          </Text>
        )}

        {/* Pays */}
        <Text style={s.label}>Contexte pays</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
          {['CM', 'SN', 'CI', 'TG'].map(p => (
            <TouchableOpacity key={p} onPress={() => setPays(p)}
              style={[s.chip, pays === p && s.chipActive]}>
              <Text style={[s.chipText, pays === p && s.chipTextActive]}>{p}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Brief */}
        <Text style={s.label}>Brief client</Text>
        <TextInput
          style={s.textarea}
          value={brief}
          onChangeText={setBrief}
          multiline
          numberOfLines={6}
          placeholder={`Ex: Flyer pour l'ouverture de ma boutique "Mode Chic" à Yaoundé. Couleurs vert et or. WhatsApp : 699 00 11 22.`}
          placeholderTextColor="#9ca3af"
          textAlignVertical="top"
        />

        <TouchableOpacity
          style={[s.btn, loading && s.btnDisabled]}
          onPress={generer}
          disabled={loading}
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>✨ Générer l'infographie</Text>}
        </TouchableOpacity>
      </View>

      {resultat && (
        <View style={s.card}>
          <Text style={s.label}>{resultat.titre || 'Infographie générée'}</Text>
          <Text style={{ color: '#16a34a', fontWeight: '600', marginBottom: 12 }}>{formatFCFA(resultat.prix_fcfa)}</Text>

          {resultat.png_base64 ? (
            <Image
              source={{ uri: `data:image/png;base64,${resultat.png_base64}` }}
              style={{ width: '100%', height: 250, borderRadius: 12 }}
              resizeMode="contain"
            />
          ) : (
            <View style={{ backgroundColor: '#f3f4f6', borderRadius: 12, padding: 20, alignItems: 'center' }}>
              <Text style={{ color: '#9ca3af', fontSize: 13 }}>
                PDF généré avec succès.{'\n'}Téléchargez via l'app web pour voir l'aperçu.
              </Text>
            </View>
          )}
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
  pickerWrap: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, marginBottom: 8, overflow: 'hidden' },
  picker: { height: 48 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: '#f3f4f6', borderWidth: 1, borderColor: '#e5e7eb' },
  chipActive: { backgroundColor: '#ea580c', borderColor: '#ea580c' },
  chipText: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  chipTextActive: { color: '#fff' },
  textarea: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 13, color: '#111827', minHeight: 130, marginBottom: 16 },
  btn: { backgroundColor: '#ea580c', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
})
