import { useState, useEffect } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, Image,
} from 'react-native'
import { Picker } from '@react-native-picker/picker'
import * as ImagePicker from 'expo-image-picker'
import { infographieAPI } from '../../src/api/client'

interface Gabarit {
  cle: string; label: string; width_mm: number; height_mm: number;
  categorie: string; prix_fcfa: number; description?: string
}

type Mode = 'brief' | 'modele' | 'custom'

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' crédits'
}

const PAYS = ['CM', 'SN', 'CI', 'TG']

const CAT_LABELS: Record<string, string> = {
  print: '🖨️ Standard',
  evenement: '🎉 Événement',
  corporate: '🏢 Corporate',
  grand_format: '📐 Grand format',
  social_media: '📱 Réseaux sociaux',
  commercial: '🛍️ Commercial',
  officiel: '📜 Officiel',
}

export default function InfographieScreen() {
  const [mode, setMode] = useState<Mode>('brief')
  const [gabarits, setGabarits] = useState<Gabarit[]>([])
  const [gabarit, setGabarit] = useState('flyer_a5')
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{ png_base64?: string; prix_fcfa?: number; titre?: string; analyse_modele?: string } | null>(null)

  // Mode modèle
  const [modeleUri, setModeleUri] = useState<string | null>(null)
  const [modeleNom, setModeleNom] = useState('')

  // Mode custom
  const [customW, setCustomW] = useState('210')
  const [customH, setCustomH] = useState('297')
  const [customBleed, setCustomBleed] = useState('3')

  useEffect(() => {
    infographieAPI.gabarits().then(r => setGabarits(r.data.gabarits)).catch(() => {})
  }, [])

  const categories = [...new Set(gabarits.map(g => g.categorie))]
  const gabaritsByCategorie = categories.reduce((acc, cat) => {
    acc[cat] = gabarits.filter(g => g.categorie === cat)
    return acc
  }, {} as Record<string, Gabarit[]>)

  const choisirImage = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync()
    if (!perm.granted) {
      Alert.alert('Permission requise', 'Autorisez l\'accès à vos photos')
      return
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: false,
      quality: 0.8,
    })
    if (!result.canceled && result.assets[0]) {
      setModeleUri(result.assets[0].uri)
      setModeleNom(result.assets[0].fileName || 'image-modele.jpg')
    }
  }

  const scannerModele = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync()
    if (!perm.granted) {
      Alert.alert('Permission requise', 'Autorisez l\'accès à la caméra')
      return
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8 })
    if (!result.canceled && result.assets[0]) {
      setModeleUri(result.assets[0].uri)
      setModeleNom('photo-modele.jpg')
    }
  }

  const generer = async () => {
    if (!brief.trim()) { Alert.alert('Erreur', 'Décrivez votre besoin'); return }
    if (mode !== 'custom' && !gabarit) { Alert.alert('Erreur', 'Choisissez un gabarit'); return }

    setLoading(true)
    setResultat(null)
    try {
      if (mode === 'brief') {
        const r = await infographieAPI.generer({ brief, type_gabarit: gabarit, pays })
        setResultat(r.data)
      } else if (mode === 'modele') {
        if (!modeleUri) { Alert.alert('Erreur', 'Sélectionnez une image modèle'); setLoading(false); return }
        const fd = new FormData()
        fd.append('modele', { uri: modeleUri, name: modeleNom, type: modeleNom.endsWith('.png') ? 'image/png' : 'image/jpeg' } as unknown as Blob)
        fd.append('brief', brief)
        fd.append('type_gabarit', gabarit)
        fd.append('pays', pays)
        const r = await infographieAPI.genererDepuisModele(fd)
        setResultat(r.data)
      } else {
        const r = await infographieAPI.genererCustom({
          width_mm: parseFloat(customW) || 210,
          height_mm: parseFloat(customH) || 297,
          bleed_mm: parseFloat(customBleed) || 3,
          brief, pays,
        })
        setResultat(r.data)
      }
      Alert.alert('Succès', 'Infographie générée !')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert('Erreur', err.response?.data?.detail || 'Génération échouée')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ScrollView style={s.container} keyboardShouldPersistTaps="handled">
      <View style={s.header}>
        <Text style={s.title}>🎨 Infographie</Text>
        <Text style={s.subtitle}>Flyers, affiches, réseaux sociaux — print-ready</Text>
      </View>

      {/* Mode tabs */}
      <View style={s.modeRow}>
        {([
          { key: 'brief', label: '✨ Brief' },
          { key: 'modele', label: '📷 Modèle' },
          { key: 'custom', label: '📐 Libre' },
        ] as { key: Mode; label: string }[]).map(m => (
          <TouchableOpacity key={m.key} onPress={() => { setMode(m.key); setResultat(null) }}
            style={[s.modeTab, mode === m.key && s.modeTabActive]}>
            <Text style={[s.modeTabText, mode === m.key && s.modeTabTextActive]}>{m.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={s.card}>
        {/* Gabarit */}
        {mode !== 'custom' && (
          <>
            <Text style={s.label}>Gabarit</Text>
            <View style={s.pickerWrap}>
              <Picker selectedValue={gabarit} onValueChange={v => setGabarit(v)} style={s.picker}>
                {categories.map(cat => (
                  <Picker.Item key={`header-${cat}`} label={`── ${CAT_LABELS[cat] || cat} ──`} value={`__${cat}`} enabled={false} />
                ))}
                {gabarits.map(g => (
                  <Picker.Item key={g.cle} label={`${g.label} (${g.width_mm}×${g.height_mm}mm)`} value={g.cle} />
                ))}
              </Picker>
            </View>
          </>
        )}

        {/* Dimensions custom */}
        {mode === 'custom' && (
          <>
            <Text style={s.label}>Dimensions personnalisées</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
              {[
                { label: 'Largeur (mm)', val: customW, set: setCustomW },
                { label: 'Hauteur (mm)', val: customH, set: setCustomH },
                { label: 'Bleed (mm)', val: customBleed, set: setCustomBleed },
              ].map(f => (
                <View key={f.label} style={{ flex: 1 }}>
                  <Text style={{ fontSize: 10, color: '#6b7280', marginBottom: 4 }}>{f.label}</Text>
                  <TextInput
                    style={[s.textarea, { minHeight: 0, height: 40, marginBottom: 0 }]}
                    value={f.val}
                    onChangeText={f.set}
                    keyboardType="numeric"
                    textAlignVertical="center"
                  />
                </View>
              ))}
            </View>
          </>
        )}

        {/* Upload image modèle */}
        {mode === 'modele' && (
          <>
            <Text style={s.label}>Image modèle</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              <TouchableOpacity style={[s.btn, { flex: 1, paddingVertical: 10 }]} onPress={choisirImage}>
                <Text style={s.btnText}>📷 Galerie</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.btn, { flex: 1, paddingVertical: 10, backgroundColor: '#374151' }]} onPress={scannerModele}>
                <Text style={s.btnText}>📸 Scanner</Text>
              </TouchableOpacity>
            </View>
            {modeleUri ? (
              <View style={{ marginBottom: 12 }}>
                <Image source={{ uri: modeleUri }} style={{ width: '100%', height: 150, borderRadius: 12 }} resizeMode="cover" />
                <Text style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{modeleNom}</Text>
                <Text style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                  L'IA analysera le style, la palette et la composition de votre modèle
                </Text>
              </View>
            ) : (
              <View style={{ backgroundColor: '#f9fafb', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 12 }}>
                <Text style={{ color: '#9ca3af', fontSize: 12 }}>Aucune image sélectionnée</Text>
              </View>
            )}
          </>
        )}

        {/* Pays */}
        <Text style={s.label}>Contexte pays</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
          {PAYS.map(p => (
            <TouchableOpacity key={p} onPress={() => setPays(p)} style={[s.chip, pays === p && s.chipActive]}>
              <Text style={[s.chipText, pays === p && s.chipTextActive]}>{p}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Brief */}
        <Text style={s.label}>
          {mode === 'modele' ? 'Brief client (contexte)' : 'Brief client'}
        </Text>
        <TextInput
          style={s.textarea}
          value={brief}
          onChangeText={setBrief}
          multiline
          numberOfLines={5}
          placeholder={mode === 'modele'
            ? "Ex: Flyer pour conférence 'Leadership Africain' à Yaoundé le 15 mars…"
            : "Ex: Flyer pour l'ouverture de ma boutique 'Mode Chic' à Akwa. 30% réduction. Tél: 699 00 11 22."}
          placeholderTextColor="#9ca3af"
          textAlignVertical="top"
        />

        <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={generer} disabled={loading}>
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>✨ Générer l'infographie</Text>}
        </TouchableOpacity>
      </View>

      {resultat && (
        <View style={s.card}>
          <Text style={s.label}>{resultat.titre || 'Infographie générée'}</Text>
          {resultat.prix_fcfa && (
            <Text style={{ color: '#16a34a', fontWeight: '600', marginBottom: 12 }}>{formatFCFA(resultat.prix_fcfa)}</Text>
          )}
          {resultat.analyse_modele && resultat.analyse_modele !== '{}' && (
            <View style={{ backgroundColor: '#fff7ed', borderRadius: 12, padding: 12, marginBottom: 12 }}>
              <Text style={{ fontSize: 11, fontWeight: '600', color: '#c2410c', marginBottom: 4 }}>Style analysé</Text>
              <Text style={{ fontSize: 11, color: '#9a3412' }} numberOfLines={4}>{resultat.analyse_modele}</Text>
            </View>
          )}
          {resultat.png_base64 ? (
            <Image
              source={{ uri: `data:image/png;base64,${resultat.png_base64}` }}
              style={{ width: '100%', height: 280, borderRadius: 12 }}
              resizeMode="contain"
            />
          ) : (
            <View style={{ backgroundColor: '#f3f4f6', borderRadius: 12, padding: 20, alignItems: 'center' }}>
              <Text style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center' }}>
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
  modeRow: { flexDirection: 'row', margin: 16, backgroundColor: '#f3f4f6', borderRadius: 14, padding: 3 },
  modeTab: { flex: 1, paddingVertical: 8, borderRadius: 11, alignItems: 'center' },
  modeTabActive: { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 },
  modeTabText: { fontSize: 12, fontWeight: '500', color: '#6b7280' },
  modeTabTextActive: { color: '#ea580c', fontWeight: '600' },
  card: { backgroundColor: '#fff', borderRadius: 20, padding: 18, marginHorizontal: 16, marginBottom: 16, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 8, elevation: 3 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  pickerWrap: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, marginBottom: 16, overflow: 'hidden' },
  picker: { height: 48 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: '#f3f4f6', borderWidth: 1, borderColor: '#e5e7eb' },
  chipActive: { backgroundColor: '#ea580c', borderColor: '#ea580c' },
  chipText: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  chipTextActive: { color: '#fff' },
  textarea: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 13, color: '#111827', minHeight: 110, marginBottom: 16 },
  btn: { backgroundColor: '#ea580c', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
})
