import { useState } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity, ActivityIndicator,
  StyleSheet, Image, Alert,
} from 'react-native'
import { useTranslation } from 'react-i18next'
import { infographieProAPI } from '../../src/api/client'

interface ResultatPro {
  projet?: { titre?: string; nombre_pages?: number; cle_projet?: string }
  pdf_base64?: string
  pages_png_base64?: string[]
  projet_json_id?: string
  cle_projet_detectee?: string
}

const PAYS = ['CM', 'SN', 'CI', 'TG']
const LANGUES = ['fr', 'en', 'es', 'pt', 'ar']

export default function DesignerProScreen() {
  const { t } = useTranslation()
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [langue, setLangue] = useState('fr')
  const [ambiance, setAmbiance] = useState<'sobre' | 'standard' | 'elegant' | 'audacieux'>('standard')
  const presetMap: Record<typeof ambiance, [number, number, number, number]> = {
    sobre:      [20, 30, 40, 30],
    standard:   [50, 50, 50, 50],
    elegant:    [60, 40, 65, 85],
    audacieux:  [90, 70, 80, 60],
  }
  const [creativite, densite, imageImp, elegance] = presetMap[ambiance]
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<ResultatPro | null>(null)
  const [pageActive, setPageActive] = useState(0)
  const [modifInstr, setModifInstr] = useState('')
  const [loadingModif, setLoadingModif] = useState(false)

  const directives = {
    creativite, densite_texte: densite,
    importance_images: imageImp, elegance,
  }

  const generer = async () => {
    if (brief.trim().length < 10) {
      Alert.alert(t('alertError', 'Erreur'), 'Décris ton projet (min 10 caractères)')
      return
    }
    setLoading(true); setResultat(null); setPageActive(0)
    try {
      const r = await infographieProAPI.genererAuto({
        brief, pays, langue,
        export_cmyk: true,
        directives_visuelles: directives,
      })
      setResultat(r.data as ResultatPro)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail || e?.message || 'Échec')
    } finally { setLoading(false) }
  }

  const modifier = async () => {
    if (!resultat?.projet_json_id) return
    if (modifInstr.trim().length < 5) return
    setLoadingModif(true)
    try {
      const r = await infographieProAPI.modifier({
        projet_id: resultat.projet_json_id,
        instructions: modifInstr,
        pays, directives_visuelles: directives,
      })
      setResultat(r.data as ResultatPro); setModifInstr(''); setPageActive(0)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail || e?.message || 'Échec')
    } finally { setLoadingModif(false) }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.h1}>{t('designerPro.heading', 'Designer Pro')}</Text>
      <Text style={styles.p}>
        {t('designerPro.subheading', "Faire-part, brochures, menus, livres photo… L'IA choisit la mise en page.")}
      </Text>

      <View style={styles.card}>
        <Text style={styles.label}>Brief</Text>
        <TextInput
          value={brief}
          onChangeText={setBrief}
          multiline
          numberOfLines={6}
          placeholder="Ex: Faire-part de décès en livret 8 pages pour M. Jean MBARGA…"
          style={styles.textarea}
        />

        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Pays</Text>
            <View style={styles.pickerRow}>
              {PAYS.map(p => (
                <TouchableOpacity key={p} onPress={() => setPays(p)}
                  style={[styles.pill, pays === p && styles.pillActive]}>
                  <Text style={pays === p ? styles.pillTextActive : styles.pillText}>{p}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Langue</Text>
            <View style={styles.pickerRow}>
              {LANGUES.map(l => (
                <TouchableOpacity key={l} onPress={() => setLangue(l)}
                  style={[styles.pill, langue === l && styles.pillActive]}>
                  <Text style={langue === l ? styles.pillTextActive : styles.pillText}>{l}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>

        <Text style={[styles.label, { marginTop: 12 }]}>Ambiance</Text>
        <View style={styles.pickerRow}>
          {(['sobre', 'standard', 'elegant', 'audacieux'] as const).map(a => (
            <TouchableOpacity key={a} onPress={() => setAmbiance(a)}
              style={[styles.pill, ambiance === a && styles.pillActive]}>
              <Text style={ambiance === a ? styles.pillTextActive : styles.pillText}>{a}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity onPress={generer} disabled={loading || !brief.trim()}
          style={[styles.btn, (loading || !brief.trim()) && styles.btnDisabled]}>
          {loading
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.btnText}>{t('designerPro.generate', 'Générer le visuel')}</Text>}
        </TouchableOpacity>
      </View>

      {resultat && (
        <View style={styles.card}>
          <Text style={styles.h2}>{resultat.projet?.titre || 'Visuel'}</Text>
          <Text style={styles.p}>
            {resultat.projet?.cle_projet || resultat.cle_projet_detectee} ·
            {' '}{resultat.projet?.nombre_pages || resultat.pages_png_base64?.length || 0} page(s)
          </Text>

          {resultat.pages_png_base64 && resultat.pages_png_base64.length > 0 && (
            <>
              <ScrollView horizontal style={{ marginVertical: 8 }}>
                {resultat.pages_png_base64.map((png, i) => (
                  <TouchableOpacity key={i} onPress={() => setPageActive(i)}
                    style={[styles.thumb, pageActive === i && styles.thumbActive]}>
                    <Image source={{ uri: `data:image/png;base64,${png}` }}
                      style={{ width: 60, height: 80 }} />
                  </TouchableOpacity>
                ))}
              </ScrollView>
              <Image source={{ uri: `data:image/png;base64,${resultat.pages_png_base64[pageActive]}` }}
                style={styles.preview} resizeMode="contain" />
            </>
          )}

          {resultat.projet_json_id && (
            <>
              <Text style={[styles.label, { marginTop: 16 }]}>
                {t('designerPro.modify', 'Modifier en langage naturel')}
              </Text>
              <TextInput
                value={modifInstr} onChangeText={setModifInstr} multiline numberOfLines={3}
                placeholder='Ex : "remplace la photo p.1, change la couleur en bleu"'
                style={styles.textarea}
              />
              <TouchableOpacity onPress={modifier} disabled={loadingModif || !modifInstr.trim()}
                style={[styles.btn, (loadingModif || !modifInstr.trim()) && styles.btnDisabled]}>
                {loadingModif
                  ? <ActivityIndicator color="#fff" />
                  : <Text style={styles.btnText}>{t('designerPro.apply', 'Appliquer')}</Text>}
              </TouchableOpacity>
            </>
          )}
        </View>
      )}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 60 },
  h1: { fontSize: 22, fontWeight: '700', color: '#92400e', marginBottom: 4 },
  h2: { fontSize: 16, fontWeight: '600', color: '#111827' },
  p: { fontSize: 13, color: '#4b5563', marginBottom: 12 },
  card: { backgroundColor: '#fff', borderRadius: 16, padding: 14, marginTop: 8,
    borderWidth: 1, borderColor: '#e5e7eb' },
  label: { fontSize: 12, fontWeight: '600', color: '#1f2937', marginBottom: 4 },
  hint: { fontSize: 10, color: '#6b7280' },
  textarea: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 12,
    padding: 10, fontSize: 14, color: '#111827', minHeight: 80, textAlignVertical: 'top' },
  row: { flexDirection: 'row', gap: 8, marginTop: 12 },
  pickerRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  pill: { paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: 999, borderWidth: 1, borderColor: '#d1d5db' },
  pillActive: { backgroundColor: '#d97706', borderColor: '#d97706' },
  pillText: { fontSize: 12, color: '#374151' },
  pillTextActive: { fontSize: 12, color: '#fff', fontWeight: '600' },
  btn: { backgroundColor: '#d97706', borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginTop: 16 },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  thumb: { borderWidth: 2, borderColor: '#e5e7eb', borderRadius: 8,
    overflow: 'hidden', marginRight: 6 },
  thumbActive: { borderColor: '#d97706' },
  preview: { width: '100%', height: 400, backgroundColor: '#f9fafb', borderRadius: 12 },
})
