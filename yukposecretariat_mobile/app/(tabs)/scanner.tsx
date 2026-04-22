import { useState } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  Image, ActivityIndicator, Alert, Share,
} from 'react-native'
import * as ImagePicker from 'expo-image-picker'
import { ocrAPI } from '../../src/api/client'

const TYPES_VALIDES = ['lettre', 'formulaire', 'recu', 'manuscrit', 'tableau']

export default function ScannerScreen() {
  const [imageUri, setImageUri] = useState<string | null>(null)
  const [typeAttendu, setTypeAttendu] = useState('')
  const [modeManuscrit, setModeManuscrit] = useState(false)
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{
    texte_structure: string; type_document: string; confiance: number
  } | null>(null)

  const prendre_photo = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync()
    if (status !== 'granted') { Alert.alert('Permission refusée', 'Autorisez l\'accès à la caméra'); return }
    const res = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsEditing: true,
    })
    if (!res.canceled) setImageUri(res.assets[0].uri)
  }

  const choisir_galerie = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
    })
    if (!res.canceled) setImageUri(res.assets[0].uri)
  }

  const scanner = async () => {
    if (!imageUri) { Alert.alert('Erreur', 'Sélectionnez une image'); return }
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('fichier', {
        uri: imageUri,
        name: 'scan.jpg',
        type: 'image/jpeg',
      } as unknown as Blob)
      if (typeAttendu) fd.append('type_attendu', typeAttendu)
      fd.append('export_word', 'true')

      const r = modeManuscrit
        ? await (async () => {
            const fd2 = new FormData()
            fd2.append('fichier', { uri: imageUri, name: 'scan.jpg', type: 'image/jpeg' } as unknown as Blob)
            fd2.append('formater_en', 'lettre')
            return ocrAPI.manuscrit(fd2)
          })()
        : await ocrAPI.scanner(fd)

      setResultat(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert('Erreur OCR', err.response?.data?.detail || 'Numérisation échouée')
    } finally {
      setLoading(false)
    }
  }

  const partager = async () => {
    if (!resultat) return
    await Share.share({ message: resultat.texte_structure, title: 'Document numérisé' })
  }

  return (
    <ScrollView style={s.container}>
      <View style={s.header}>
        <Text style={s.title}>📷 Scan → Texte</Text>
        <Text style={s.subtitle}>Numérisez n'importe quel document</Text>
      </View>

      <View style={s.card}>
        {/* Mode */}
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
          <TouchableOpacity
            style={[s.modeBtn, !modeManuscrit && s.modeBtnActive]}
            onPress={() => setModeManuscrit(false)}
          >
            <Text style={[s.modeBtnText, !modeManuscrit && s.modeBtnTextActive]}>Document</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.modeBtn, modeManuscrit && s.modeBtnActive]}
            onPress={() => setModeManuscrit(true)}
          >
            <Text style={[s.modeBtnText, modeManuscrit && s.modeBtnTextActive]}>✍️ Manuscrit</Text>
          </TouchableOpacity>
        </View>

        {/* Image */}
        {imageUri ? (
          <Image source={{ uri: imageUri }} style={s.preview} resizeMode="contain" />
        ) : (
          <View style={s.placeholder}>
            <Text style={{ fontSize: 40 }}>📄</Text>
            <Text style={s.placeholderText}>Aucune image sélectionnée</Text>
          </View>
        )}

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
          <TouchableOpacity style={[s.btn, { flex: 1, backgroundColor: '#374151' }]} onPress={prendre_photo}>
            <Text style={s.btnText}>📷 Appareil photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.btn, { flex: 1, backgroundColor: '#6b7280' }]} onPress={choisir_galerie}>
            <Text style={s.btnText}>🖼 Galerie</Text>
          </TouchableOpacity>
        </View>

        {/* Type attendu */}
        {!modeManuscrit && (
          <>
            <Text style={[s.label, { marginTop: 16 }]}>Type de document</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => setTypeAttendu('')}
                  style={[s.chip, !typeAttendu && s.chipActive]}
                >
                  <Text style={[s.chipText, !typeAttendu && s.chipTextActive]}>Auto</Text>
                </TouchableOpacity>
                {TYPES_VALIDES.map(t => (
                  <TouchableOpacity
                    key={t}
                    onPress={() => setTypeAttendu(t)}
                    style={[s.chip, typeAttendu === t && s.chipActive]}
                  >
                    <Text style={[s.chipText, typeAttendu === t && s.chipTextActive]}>{t}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
          </>
        )}

        <TouchableOpacity
          style={[s.btn, { backgroundColor: '#16a34a', marginTop: 16 }, loading && s.btnDisabled]}
          onPress={scanner}
          disabled={loading || !imageUri}
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>🔍 Numériser</Text>}
        </TouchableOpacity>
      </View>

      {resultat && (
        <View style={s.card}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 }}>
            <Text style={s.badge}>{resultat.type_document}</Text>
            <Text style={{ fontSize: 12, color: '#6b7280' }}>
              Confiance : {Math.round(resultat.confiance * 100)}%
            </Text>
          </View>
          <Text style={s.markdown}>{resultat.texte_structure}</Text>
          <TouchableOpacity style={[s.btn, { backgroundColor: '#7c3aed', marginTop: 12 }]} onPress={partager}>
            <Text style={s.btnText}>📤 Partager</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  header: { backgroundColor: '#16a34a', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 },
  title: { fontSize: 22, fontWeight: '700', color: '#fff' },
  subtitle: { fontSize: 13, color: '#bbf7d0', marginTop: 4 },
  card: {
    backgroundColor: '#fff', borderRadius: 20, padding: 18, margin: 16,
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 8, elevation: 3,
  },
  modeBtn: {
    flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
    backgroundColor: '#f3f4f6', borderWidth: 1, borderColor: '#e5e7eb',
  },
  modeBtnActive: { backgroundColor: '#16a34a', borderColor: '#16a34a' },
  modeBtnText: { fontSize: 13, fontWeight: '600', color: '#6b7280' },
  modeBtnTextActive: { color: '#fff' },
  preview: { width: '100%', height: 200, borderRadius: 12, backgroundColor: '#f3f4f6' },
  placeholder: {
    height: 150, borderRadius: 12, backgroundColor: '#f3f4f6',
    alignItems: 'center', justifyContent: 'center',
  },
  placeholderText: { fontSize: 13, color: '#9ca3af', marginTop: 8 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, backgroundColor: '#f3f4f6', borderWidth: 1, borderColor: '#e5e7eb' },
  chipActive: { backgroundColor: '#16a34a', borderColor: '#16a34a' },
  chipText: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  chipTextActive: { color: '#fff' },
  btn: { backgroundColor: '#2563eb', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  badge: { fontSize: 11, backgroundColor: '#eff6ff', color: '#2563eb', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, fontWeight: '600' },
  markdown: { fontSize: 13, color: '#374151', lineHeight: 20 },
})
