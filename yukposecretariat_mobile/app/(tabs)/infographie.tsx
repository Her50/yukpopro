import { useState, useEffect } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, Image, Linking,
} from 'react-native'
import { Picker } from '@react-native-picker/picker'
import * as ImagePicker from 'expo-image-picker'
import { useTranslation } from 'react-i18next'
import { router } from 'expo-router'
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

interface Resultat {
  fichier_id?: string;
  pdf_id?: string; png_id?: string;
  pdf_cmyk_id?: string; png_preview_id?: string; svg_id?: string;
  pdf_base64?: string; png_base64?: string;
  pdf_cmyk_base64?: string; png_preview_base64?: string; svg_base64?: string;
  prix_fcfa?: number; titre?: string; analyse_modele?: string;
  justification_direction?: string; direction?: string;
}

interface Variante { direction?: string; resultat?: Resultat; [k: string]: any }

export default function InfographieScreen() {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('brief')
  const [gabarits, setGabarits] = useState<Gabarit[]>([])
  const [gabarit, setGabarit] = useState('flyer_a5')
  const [brief, setBrief] = useState('')
  const [pays, setPays] = useState('CM')
  const [loading, setLoading] = useState(false)
  const [loadingVariantes, setLoadingVariantes] = useState(false)
  const [loadingRetouche, setLoadingRetouche] = useState(false)
  const [resultat, setResultat] = useState<Resultat | null>(null)
  const [variantes, setVariantes] = useState<Variante[] | null>(null)
  const [varianteActive, setVarianteActive] = useState(0)
  const [retoucheInstr, setRetoucheInstr] = useState('')

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
      Alert.alert(t('infographie.permissionRequired'), t('infographie.permissionPhotos'))
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
      Alert.alert(t('infographie.permissionRequired'), t('infographie.permissionCamera'))
      return
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8 })
    if (!result.canceled && result.assets[0]) {
      setModeleUri(result.assets[0].uri)
      setModeleNom('photo-modele.jpg')
    }
  }

  const generer = async () => {
    if (!brief.trim()) { Alert.alert(t('infographie.alertError'), t('infographie.errDescribe')); return }
    if (mode !== 'custom' && !gabarit) { Alert.alert(t('infographie.alertError'), t('infographie.errChooseGabarit')); return }

    setLoading(true)
    setResultat(null)
    setVariantes(null)
    try {
      if (mode === 'brief') {
        const r = await infographieAPI.generer({ brief, type_gabarit: gabarit, pays, export_cmyk: true, export_svg: true })
        setResultat(r.data)
      } else if (mode === 'modele') {
        if (!modeleUri) { Alert.alert(t('infographie.alertError'), t('infographie.errSelectImage')); setLoading(false); return }
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
          brief, pays, export_cmyk: true, export_svg: true,
        })
        setResultat(r.data)
      }
      Alert.alert(t('infographie.alertSuccess'), t('infographie.okGenerated'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert(t('infographie.alertError'), err.response?.data?.detail || t('infographie.errGen'))
    } finally {
      setLoading(false)
    }
  }

  const genererVariantes = async () => {
    if (!brief.trim()) { Alert.alert(t('infographie.alertError'), t('infographie.errDescribe')); return }
    if (!gabarit) { Alert.alert(t('infographie.alertError'), t('infographie.errChooseGabarit')); return }
    setLoadingVariantes(true); setVariantes(null); setResultat(null)
    try {
      const r = await infographieAPI.genererVariantes({ brief, type_gabarit: gabarit, pays, nombre: 4 })
      const list: Variante[] = r.data?.variantes ?? r.data?.results ?? []
      if (!list.length) throw new Error(t('infographie.variantsErr'))
      setVariantes(list)
      setVarianteActive(0)
      const first = list[0]?.resultat ?? (list[0] as Resultat)
      if (first) setResultat(first)
      Alert.alert(t('infographie.alertSuccess'), `${list.length} ${t('infographie.variantsOk')}`)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      Alert.alert(t('infographie.alertError'), err.response?.data?.detail || err.message || t('infographie.variantsErrLabel'))
    } finally { setLoadingVariantes(false) }
  }

  const choisirVariante = (idx: number) => {
    if (!variantes || !variantes[idx]) return
    setVarianteActive(idx)
    const r = variantes[idx]?.resultat ?? (variantes[idx] as Resultat)
    if (r) setResultat(r)
  }

  const retoucher = async () => {
    const fid = resultat?.fichier_id || resultat?.pdf_id || resultat?.png_id
    if (!fid) { Alert.alert(t('infographie.alertError'), t('infographie.retouchErrEmpty')); return }
    if (!retoucheInstr.trim()) { Alert.alert(t('infographie.alertError'), t('infographie.retouchErrEmptyInstr')); return }
    setLoadingRetouche(true)
    try {
      const r = await infographieAPI.modifier({ fichier_id: fid, instructions: retoucheInstr, pays })
      setResultat(r.data)
      setRetoucheInstr('')
      Alert.alert(t('infographie.alertSuccess'), t('infographie.retouchOk'))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      Alert.alert(t('infographie.alertError'), err.response?.data?.detail || err.message || t('infographie.retouchErr'))
    } finally { setLoadingRetouche(false) }
  }

  const ouvrirFichier = (fid?: string) => {
    if (!fid) return
    Linking.openURL(infographieAPI.telechargerUrl(fid))
  }

  return (
    <ScrollView style={s.container} keyboardShouldPersistTaps="handled">
      <View style={s.header}>
        <Text style={s.title}>{t('infographie.titleMobile')}</Text>
        <Text style={s.subtitle}>{t('infographie.subtitleMobile')}</Text>
        <TouchableOpacity
          onPress={() => router.push('/designer-pro')}
          style={{ marginTop: 8, backgroundColor: '#f97316', paddingVertical: 10,
            borderRadius: 12, alignItems: 'center' }}>
          <Text style={{ color: '#fff', fontWeight: '600', fontSize: 13 }}>
            ✨ Designer Pro — visuels multi-page (IA)
          </Text>
        </TouchableOpacity>
      </View>

      {/* Mode tabs */}
      <View style={s.modeRow}>
        {([
          { key: 'brief', label: t('infographie.modeBriefShort') },
          { key: 'modele', label: t('infographie.modeModeleShort') },
          { key: 'custom', label: t('infographie.modeCustomShort') },
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
            <Text style={s.label}>{t('infographie.labelGabarit')}</Text>
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
            <Text style={s.label}>{t('infographie.labelDimensions')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
              {[
                { label: t('infographie.labelWidth'), val: customW, set: setCustomW },
                { label: t('infographie.labelHeight'), val: customH, set: setCustomH },
                { label: t('infographie.labelBleedShort'), val: customBleed, set: setCustomBleed },
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
            <Text style={s.label}>{t('infographie.labelModeleShort')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              <TouchableOpacity style={[s.btn, { flex: 1, paddingVertical: 10 }]} onPress={choisirImage}>
                <Text style={s.btnText}>{t('infographie.btnGallery')}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.btn, { flex: 1, paddingVertical: 10, backgroundColor: '#374151' }]} onPress={scannerModele}>
                <Text style={s.btnText}>{t('infographie.btnScan')}</Text>
              </TouchableOpacity>
            </View>
            {modeleUri ? (
              <View style={{ marginBottom: 12 }}>
                <Image source={{ uri: modeleUri }} style={{ width: '100%', height: 150, borderRadius: 12 }} resizeMode="cover" />
                <Text style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{modeleNom}</Text>
                <Text style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                  {t('infographie.modeleAnalyseShort')}
                </Text>
              </View>
            ) : (
              <View style={{ backgroundColor: '#f9fafb', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 12 }}>
                <Text style={{ color: '#9ca3af', fontSize: 12 }}>{t('infographie.noImage')}</Text>
              </View>
            )}
          </>
        )}

        {/* Pays */}
        <Text style={s.label}>{t('infographie.labelCountryContext')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
          {PAYS.map(p => (
            <TouchableOpacity key={p} onPress={() => setPays(p)} style={[s.chip, pays === p && s.chipActive]}>
              <Text style={[s.chipText, pays === p && s.chipTextActive]}>{p}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Brief */}
        <Text style={s.label}>
          {mode === 'modele' ? t('infographie.labelBriefModeleShort') : t('infographie.labelBrief')}
        </Text>
        <TextInput
          style={s.textarea}
          value={brief}
          onChangeText={setBrief}
          multiline
          numberOfLines={5}
          placeholder={mode === 'modele' ? t('infographie.briefPlaceholderModele') : t('infographie.briefPlaceholder')}
          placeholderTextColor="#9ca3af"
          textAlignVertical="top"
        />

        <View style={mode === 'brief' ? { flexDirection: 'row', gap: 8 } : undefined}>
          <TouchableOpacity style={[s.btn, { flex: 1 }, (loading || loadingVariantes) && s.btnDisabled]} onPress={generer} disabled={loading || loadingVariantes}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>{t('infographie.oneVisualShort')}</Text>}
          </TouchableOpacity>
          {mode === 'brief' && (
            <TouchableOpacity style={[s.btn, { flex: 1, backgroundColor: '#ec4899' }, (loading || loadingVariantes) && s.btnDisabled]} onPress={genererVariantes} disabled={loading || loadingVariantes}>
              {loadingVariantes ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>{t('infographie.fourVariantsShort')}</Text>}
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Galerie variantes */}
      {variantes && variantes.length > 1 && (
        <View style={s.card}>
          <Text style={[s.label, { color: '#ec4899' }]}>✨ {variantes.length} {t('infographie.variantsTitleShort')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {variantes.map((v, idx) => {
              const r = v?.resultat ?? (v as Resultat)
              const preview = r?.png_base64 || r?.png_preview_base64
              const active = varianteActive === idx
              return (
                <TouchableOpacity key={idx} onPress={() => choisirVariante(idx)}
                  style={{ width: '48%', aspectRatio: 1, borderRadius: 12, borderWidth: 2, borderColor: active ? '#ec4899' : '#e5e7eb', overflow: 'hidden', backgroundColor: '#f9fafb' }}>
                  {preview ? (
                    <Image source={{ uri: `data:image/png;base64,${preview}` }} style={{ flex: 1 }} resizeMode="cover" />
                  ) : (
                    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: '#9ca3af', fontSize: 11 }}>N°{idx + 1}</Text>
                    </View>
                  )}
                  <View style={{ position: 'absolute', top: 4, left: 4, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                    <Text style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>N°{idx + 1}</Text>
                  </View>
                </TouchableOpacity>
              )
            })}
          </View>
        </View>
      )}

      {resultat && (
        <View style={s.card}>
          <Text style={s.label}>{resultat.titre || t('infographie.titleGenerated')}</Text>
          {resultat.prix_fcfa && (
            <Text style={{ color: '#16a34a', fontWeight: '600', marginBottom: 12 }}>{formatFCFA(resultat.prix_fcfa)}</Text>
          )}
          {resultat.analyse_modele && resultat.analyse_modele !== '{}' && (
            <View style={{ backgroundColor: '#fff7ed', borderRadius: 12, padding: 12, marginBottom: 12 }}>
              <Text style={{ fontSize: 11, fontWeight: '600', color: '#c2410c', marginBottom: 4 }}>{t('infographie.styleAnalyzed')}</Text>
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
                {t('infographie.pdfGeneratedDownload')}
              </Text>
            </View>
          )}

          {/* Téléchargements */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            {resultat.pdf_id && (
              <TouchableOpacity onPress={() => ouvrirFichier(resultat.pdf_id)}
                style={{ flexBasis: '48%', flexGrow: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: '#ef4444' }}>
                <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{t('infographie.pdfRgbMobile')}</Text>
              </TouchableOpacity>
            )}
            {resultat.pdf_cmyk_id && (
              <TouchableOpacity onPress={() => ouvrirFichier(resultat.pdf_cmyk_id)}
                style={{ flexBasis: '48%', flexGrow: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: '#d97706' }}>
                <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{t('infographie.pdfCmykMobile')}</Text>
              </TouchableOpacity>
            )}
            {resultat.svg_id && (
              <TouchableOpacity onPress={() => ouvrirFichier(resultat.svg_id)}
                style={{ flexBasis: '48%', flexGrow: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: '#059669' }}>
                <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{t('infographie.svgMobile')}</Text>
              </TouchableOpacity>
            )}
            {(resultat.png_preview_id || resultat.png_id) && (
              <TouchableOpacity onPress={() => ouvrirFichier(resultat.png_preview_id || resultat.png_id)}
                style={{ flexBasis: '48%', flexGrow: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center', backgroundColor: '#2563eb' }}>
                <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{t('infographie.pngHdMobile')}</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Retouche IA */}
          {(resultat.fichier_id || resultat.pdf_id || resultat.png_id) && (
            <View style={{ marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: '#f3f4f6' }}>
              <Text style={[s.label, { color: '#ea580c' }]}>{t('infographie.retouchTitleMobile')}</Text>
              <TextInput
                style={[s.textarea, { minHeight: 60 }]}
                placeholder={t('infographie.retouchPlaceholderMobile')}
                placeholderTextColor="#9ca3af"
                value={retoucheInstr}
                onChangeText={setRetoucheInstr}
                multiline
              />
              <TouchableOpacity onPress={retoucher} disabled={loadingRetouche || !retoucheInstr.trim()}
                style={[s.btn, { paddingVertical: 11 }, (loadingRetouche || !retoucheInstr.trim()) && s.btnDisabled]}>
                {loadingRetouche ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>{t('infographie.retouchApplyMobile')}</Text>}
              </TouchableOpacity>
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
