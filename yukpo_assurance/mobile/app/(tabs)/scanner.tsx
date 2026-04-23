/**
 * Scanner OCR — Mode scan de document optimisé
 * Overlay avec guidelines (coins + zone de cadrage), aspect ratio A4,
 * conseils de prise en main, analyse OCR automatique.
 */
import { useState, useRef } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Image, ActivityIndicator, Alert, Dimensions, Animated,
} from 'react-native'
import * as ImagePicker from 'expo-image-picker'
import { CameraView, useCameraPermissions } from 'expo-camera'
import { Ionicons } from '@expo/vector-icons'
import { ocrAPI } from '../../src/api/client'
import { DemoBanner } from '../../src/components/DemoBanner'

const SCREEN_W = Dimensions.get('window').width

// ─── Types ────────────────────────────────────────────────────────────────────

interface ResultatOCR {
  type: string
  champs: Record<string, string>
  confiance: number
  champs_orass?: Record<string, string>
}

// ─── Config types documents ───────────────────────────────────────────────────

const TYPES_DOCUMENT = [
  { value: 'cni', label: 'CNI / Passeport', icon: 'card-outline', couleur: '#3b82f6',
    hint: 'Placez la CNI bien à plat, tous les coins visibles', ratio: 1.587 },
  { value: 'carte_grise', label: 'Carte grise', icon: 'car-outline', couleur: '#10b981',
    hint: 'Document rectangulaire horizontal — assurez un bon éclairage', ratio: 1.414 },
  { value: 'facture_garage', label: 'Facture garage', icon: 'construct-outline', couleur: '#f59e0b',
    hint: 'Feuille A4 — centrez le document, évitez les ombres', ratio: 0.707 },
  { value: 'facture_hopital', label: 'Facture médicale', icon: 'medkit-outline', couleur: '#ef4444',
    hint: 'Feuille A4 — posez sur une surface plane et bien éclairée', ratio: 0.707 },
  { value: 'constat_amiable', label: 'Constat amiable', icon: 'document-outline', couleur: '#8b5cf6',
    hint: 'Document A4 double face — scannez chaque face séparément', ratio: 0.707 },
  { value: 'certificat_medical', label: 'Certificat médical', icon: 'fitness-outline', couleur: '#ec4899',
    hint: 'Document A4 ou A5 — assurez la lisibilité du tampon', ratio: 0.707 },
  { value: 'carte_assurance', label: 'Carte assurance', icon: 'shield-outline', couleur: '#0ea5e9',
    hint: 'Format carte bancaire — placez sur fond sombre', ratio: 1.587 },
  { value: 'autre', label: 'Autre document', icon: 'copy-outline', couleur: '#64748b',
    hint: 'Cadrez au maximum le document dans la zone de scan', ratio: 0.707 },
]

// ─── Données démo OCR ─────────────────────────────────────────────────────────

const DEMO_OCR: Record<string, ResultatOCR> = {
  cni: { type: 'CNI', confiance: 0.94, champs: { NOM: 'NKENG', PRENOM: 'Paul André', DATE_NAISSANCE: '15/08/1988', NUMERO_CNI: 'CM-2024-789012', LIEU_NAISSANCE: 'Bafoussam', VALIDITE: '15/08/2029' }, champs_orass: { ASSURE_NOM: 'NKENG', ASSURE_PRENOM: 'Paul André', ASSURE_DATE_NAISS: '15/08/1988' } },
  carte_grise: { type: 'Carte Grise', confiance: 0.91, champs: { MARQUE: 'Toyota', MODELE: 'Corolla', IMMATRICULATION: 'LT-456-DLA', ANNEE: '2019', PUISSANCE: '90 CV', PROPRIETAIRE: 'NKENG Paul' }, champs_orass: { VEHICULE_MARQUE: 'Toyota', VEHICULE_MODELE: 'Corolla', VEHICULE_IMMAT: 'LT-456-DLA' } },
  facture_garage: { type: 'Facture Garage', confiance: 0.88, champs: { FOURNISSEUR: 'Garage Toyota Douala', NUMERO: 'FAC-2024-0892', DATE: '15/03/2026', MONTANT_HT: '420 000 XAF', TVA: '65 000 XAF', MONTANT_TTC: '485 000 XAF' }, champs_orass: { SINISTRE_MONTANT: '485000', COMPTE_PCSA: '6150' } },
  facture_hopital: { type: 'Facture Médicale', confiance: 0.90, champs: { ETABLISSEMENT: 'Clinique Centrale YDE', PATIENT: 'MBARGA Jean', DATE_SOINS: '10/04/2026', ACTES: 'Consultation + Rx', MONTANT: '125 000 XAF' }, champs_orass: { SINISTRE_MONTANT: '125000', COMPTE_PCSA: '6180', BRANCHE: 'B80' } },
  constat_amiable: { type: 'Constat Amiable', confiance: 0.85, champs: { DATE_ACCIDENT: '08/04/2026', CONDUCTEUR_A: 'NKENG Paul — LT-456-DLA', CONDUCTEUR_B: 'FOGUE Henri — YA-789-CD', LIEU: 'Carrefour Nlongkak, Yaoundé', CIRCONSTANCES: 'Collision arrière au feu rouge' }, champs_orass: { SINISTRE_DATE: '08/04/2026', TIERS_NOM: 'FOGUE Henri', TIERS_VEHICULE: 'YA-789-CD' } },
  default: { type: 'Document', confiance: 0.87, champs: { TYPE_DETECTE: 'Document standard', DATE: '10/04/2026', STATUT: 'Analysé par YukpoPro' }, champs_orass: {} },
}

// ─── Overlay guidage scan ──────────────────────────────────────────────────────

function DocumentOverlay({ ratio, couleur, hint }: { ratio: number; couleur: string; hint: string }) {
  const boxW = SCREEN_W - 48
  const boxH = boxW / ratio
  const cornerSize = 24
  const cornerThick = 3

  const cornerStyle = (pos: 'tl' | 'tr' | 'bl' | 'br') => {
    const base: object = { position: 'absolute', width: cornerSize, height: cornerSize }
    const borders = {
      tl: { top: 0, left: 0, borderTopWidth: cornerThick, borderLeftWidth: cornerThick, borderTopLeftRadius: 4 },
      tr: { top: 0, right: 0, borderTopWidth: cornerThick, borderRightWidth: cornerThick, borderTopRightRadius: 4 },
      bl: { bottom: 0, left: 0, borderBottomWidth: cornerThick, borderLeftWidth: cornerThick, borderBottomLeftRadius: 4 },
      br: { bottom: 0, right: 0, borderBottomWidth: cornerThick, borderRightWidth: cornerThick, borderBottomRightRadius: 4 },
    }
    return [base, borders[pos], { borderColor: couleur }]
  }

  return (
    <View style={{ alignItems: 'center', paddingVertical: 16 }}>
      {/* Zone de cadrage */}
      <View style={{
        width: boxW, height: boxH,
        borderWidth: 1.5, borderColor: couleur + '60',
        borderRadius: 8,
        position: 'relative',
        backgroundColor: couleur + '08',
        justifyContent: 'center', alignItems: 'center',
      }}>
        {/* Coins actifs */}
        {(['tl', 'tr', 'bl', 'br'] as const).map(p => (
          <View key={p} style={cornerStyle(p) as never} />
        ))}

        {/* Grille légère (règle des tiers) */}
        <View style={{ position: 'absolute', top: '33%', left: 0, right: 0, height: 0.5, backgroundColor: couleur + '30' }} />
        <View style={{ position: 'absolute', top: '66%', left: 0, right: 0, height: 0.5, backgroundColor: couleur + '30' }} />
        <View style={{ position: 'absolute', left: '33%', top: 0, bottom: 0, width: 0.5, backgroundColor: couleur + '30' }} />
        <View style={{ position: 'absolute', left: '66%', top: 0, bottom: 0, width: 0.5, backgroundColor: couleur + '30' }} />

        {/* Label centre */}
        <View style={{ backgroundColor: couleur + '20', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20 }}>
          <Text style={{ fontSize: 12, color: couleur, fontWeight: '700' }}>Cadrez le document ici</Text>
        </View>
      </View>

      {/* Conseil */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, paddingHorizontal: 8 }}>
        <Ionicons name="information-circle-outline" size={14} color={couleur} />
        <Text style={{ fontSize: 11, color: '#64748b', flex: 1 }}>{hint}</Text>
      </View>
    </View>
  )
}

// ─── Résultat OCR ──────────────────────────────────────────────────────────────

function ResultatOCRView({ resultat, onReset, isDemo }: { resultat: ResultatOCR; onReset: () => void; isDemo: boolean }) {
  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      {isDemo && <DemoBanner message="Résultat de démonstration — l'API OCR n'a pas répondu. Reprenez une photo ou vérifiez la connexion." />}
      {/* Header confiance */}
      <View style={[rs.confianceCard, { backgroundColor: resultat.confiance > 0.9 ? '#f0fdf4' : '#fffbeb', borderColor: resultat.confiance > 0.9 ? '#bbf7d0' : '#fde68a' }]}>
        <Ionicons name={resultat.confiance > 0.9 ? 'checkmark-circle' : 'alert-circle'} size={20} color={resultat.confiance > 0.9 ? '#16a34a' : '#92400e'} />
        <View style={{ flex: 1 }}>
          <Text style={[rs.confianceTitre, { color: resultat.confiance > 0.9 ? '#15803d' : '#78350f' }]}>
            {resultat.type} — Confiance {Math.round(resultat.confiance * 100)}%
          </Text>
          <Text style={{ fontSize: 11, color: '#64748b' }}>Analyse Yukpo · Zone CIMA</Text>
        </View>
      </View>

      {/* Champs extraits */}
      <View style={rs.card}>
        <Text style={rs.cardTitle}>Champs extraits</Text>
        {Object.entries(resultat.champs).map(([k, v]) => (
          <View key={k} style={rs.champRow}>
            <Text style={rs.champKey}>{k.replace(/_/g, ' ')}</Text>
            <Text style={rs.champVal}>{v}</Text>
          </View>
        ))}
      </View>

      {/* Champs ORASS */}
      {resultat.champs_orass && Object.keys(resultat.champs_orass).length > 0 && (
        <View style={[rs.card, { backgroundColor: '#eff6ff', borderColor: '#bfdbfe' }]}>
          <Text style={[rs.cardTitle, { color: '#1d4ed8' }]}>Champs ORASS / Mercure mappés</Text>
          {Object.entries(resultat.champs_orass).map(([k, v]) => (
            <View key={k} style={rs.champRow}>
              <Text style={[rs.champKey, { fontFamily: 'monospace', fontSize: 11, color: '#1d4ed8' }]}>{k}</Text>
              <Text style={[rs.champVal, { color: '#1d4ed8' }]}>{v}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Actions */}
      <View style={{ gap: 10 }}>
        <TouchableOpacity style={[rs.actionBtn, { backgroundColor: '#1d4ed8' }]}>
          <Ionicons name="cloud-upload-outline" size={16} color="#fff" />
          <Text style={rs.actionText}>Importer dans ORASS / Mercure</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[rs.actionBtn, { backgroundColor: '#10b981' }]}>
          <Ionicons name="copy-outline" size={16} color="#fff" />
          <Text style={rs.actionText}>Pré-remplir le formulaire</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[rs.actionBtn, { backgroundColor: '#6b7280' }]} onPress={onReset}>
          <Ionicons name="camera-outline" size={16} color="#fff" />
          <Text style={rs.actionText}>Scanner un autre document</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  )
}

// ─── Écran principal ──────────────────────────────────────────────────────────

export default function ScannerScreen() {
  const [typeSelectionne, setTypeSelectionne] = useState('cni')
  const [imageUri, setImageUri] = useState<string | null>(null)
  const [resultat, setResultat] = useState<ResultatOCR | null>(null)
  const [isDemoResult, setIsDemoResult] = useState(false)
  const [loading, setLoading] = useState(false)
  const [cameraPermission, requestPermission] = useCameraPermissions()
  const [modeCamera, setModeCamera] = useState(false)
  const cameraRef = useRef<CameraView>(null)

  const typeInfo = TYPES_DOCUMENT.find(t => t.value === typeSelectionne) ?? TYPES_DOCUMENT[0]

  const analyserDocument = async (uri: string) => {
    setLoading(true)
    setResultat(null)
    try {
      let data: ResultatOCR
      if (typeSelectionne === 'cni') data = await ocrAPI.analyserCNI(uri)
      else if (typeSelectionne === 'carte_grise') data = await ocrAPI.analyserCarteGrise(uri)
      else data = await ocrAPI.analyserImage(uri, typeSelectionne)
      setResultat(data)
      setIsDemoResult(false)
    } catch {
      setResultat(DEMO_OCR[typeSelectionne] ?? DEMO_OCR.default)
      setIsDemoResult(true)
    } finally {
      setLoading(false)
    }
  }

  const prendrePhotoCamera = async () => {
    if (!cameraPermission?.granted) {
      const { granted } = await requestPermission()
      if (!granted) { Alert.alert('Permission refusée', 'La caméra est nécessaire.'); return }
    }
    setModeCamera(true)
  }

  const capturerPhoto = async () => {
    if (!cameraRef.current) return
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.92,
        skipProcessing: false,
      })
      if (photo?.uri) {
        setModeCamera(false)
        setImageUri(photo.uri)
        analyserDocument(photo.uri)
      }
    } catch (e) {
      Alert.alert('Erreur', 'Impossible de prendre la photo.')
    }
  }

  const choisirGalerie = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.9 })
    if (!result.canceled && result.assets[0]) {
      setImageUri(result.assets[0].uri)
      analyserDocument(result.assets[0].uri)
    }
  }

  const reset = () => { setImageUri(null); setResultat(null); setIsDemoResult(false) }

  // ── Mode caméra en plein écran ─────────────────────────────────────────────
  if (modeCamera) {
    const boxW = SCREEN_W - 40
    const boxH = boxW / typeInfo.ratio
    return (
      <View style={{ flex: 1, backgroundColor: '#000' }}>
        <CameraView
          ref={cameraRef}
          style={{ flex: 1 }}
          facing="back"
          pictureSize="1920x1080"
        >
          {/* Overlay sombre autour de la zone */}
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            {/* Zone de cadrage */}
            <View style={{
              width: boxW, height: boxH,
              borderWidth: 2, borderColor: typeInfo.couleur,
              borderRadius: 8, overflow: 'hidden',
            }}>
              {/* Coins */}
              {([
                { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderColor: '#fff', borderTopLeftRadius: 6 },
                { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderColor: '#fff', borderTopRightRadius: 6 },
                { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderColor: '#fff', borderBottomLeftRadius: 6 },
                { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderColor: '#fff', borderBottomRightRadius: 6 },
              ] as object[]).map((c, i) => (
                <View key={i} style={[{ position: 'absolute', width: 28, height: 28 }, c]} />
              ))}
            </View>
            {/* Conseil */}
            <View style={{ marginTop: 16, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }}>
              <Text style={{ color: '#fff', fontSize: 12, textAlign: 'center' }}>{typeInfo.hint}</Text>
            </View>
          </View>

          {/* Barre basse */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 30, paddingBottom: 50, paddingTop: 20 }}>
            <TouchableOpacity onPress={() => setModeCamera(false)} style={{ padding: 12 }}>
              <Ionicons name="close-circle-outline" size={32} color="#fff" />
            </TouchableOpacity>
            {/* Bouton déclencheur */}
            <TouchableOpacity onPress={capturerPhoto} style={cam.shutterOuter}>
              <View style={cam.shutterInner} />
            </TouchableOpacity>
            <TouchableOpacity onPress={choisirGalerie} style={{ padding: 12 }}>
              <Ionicons name="images-outline" size={28} color="#fff" />
            </TouchableOpacity>
          </View>
        </CameraView>
      </View>
    )
  }

  // ── Vue principale ─────────────────────────────────────────────────────────
  if (resultat && !loading) {
    return <ResultatOCRView resultat={resultat} onReset={reset} isDemo={isDemoResult} />
  }

  return (
    <ScrollView style={{ flex: 1, backgroundColor: '#f1f5f9' }}>

      {/* Sélection type document */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Type de document</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {TYPES_DOCUMENT.map(t => (
            <TouchableOpacity
              key={t.value}
              style={[styles.typeBtn, typeSelectionne === t.value && {
                borderColor: t.couleur, backgroundColor: t.couleur + '15',
              }]}
              onPress={() => { setTypeSelectionne(t.value); setResultat(null); setImageUri(null) }}
            >
              <Ionicons name={t.icon as never} size={20} color={typeSelectionne === t.value ? t.couleur : '#94a3b8'} />
              <Text style={[styles.typeBtnText, typeSelectionne === t.value && { color: t.couleur, fontWeight: '700' }]}>
                {t.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Zone cadrage + capture */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Zone de scan</Text>

        {imageUri ? (
          <View style={{ alignItems: 'center' }}>
            <Image source={{ uri: imageUri }} style={styles.preview} resizeMode="contain" />
            <TouchableOpacity style={styles.retakeBtn} onPress={reset}>
              <Ionicons name="refresh-outline" size={16} color="#fff" />
              <Text style={{ color: '#fff', fontWeight: '600', fontSize: 13 }}>Nouvelle prise</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            <DocumentOverlay ratio={typeInfo.ratio} couleur={typeInfo.couleur} hint={typeInfo.hint} />

            <View style={{ gap: 10, marginTop: 4 }}>
              <TouchableOpacity
                style={[styles.captureBtn, { backgroundColor: typeInfo.couleur }]}
                onPress={prendrePhotoCamera}
              >
                <Ionicons name="camera" size={22} color="#fff" />
                <Text style={styles.captureBtnText}>Scanner avec la caméra</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.galleryBtn} onPress={choisirGalerie}>
                <Ionicons name="images-outline" size={18} color="#374151" />
                <Text style={styles.galleryBtnText}>Importer depuis la galerie</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>

      {/* Loading OCR */}
      {loading && (
        <View style={styles.loadingCard}>
          <ActivityIndicator size="large" color="#1d4ed8" />
          <Text style={{ fontSize: 14, fontWeight: '600', color: '#374151', marginTop: 12 }}>Analyse OCR en cours…</Text>
          <Text style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>Powered by Yukpo · Expert CIMA</Text>
        </View>
      )}
    </ScrollView>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  section: { backgroundColor: '#fff', borderRadius: 12, margin: 12, padding: 16, elevation: 1, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 2 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#1e293b', marginBottom: 12 },
  typeBtn: { borderWidth: 1.5, borderColor: '#e2e8f0', borderRadius: 10, padding: 10, alignItems: 'center', width: '30%' },
  typeBtnText: { fontSize: 10, color: '#64748b', marginTop: 4, textAlign: 'center' },
  captureBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, borderRadius: 12, paddingVertical: 15 },
  captureBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  galleryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 12, paddingVertical: 13, backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0' },
  galleryBtnText: { color: '#374151', fontWeight: '600', fontSize: 14 },
  preview: { width: SCREEN_W - 64, height: 220, borderRadius: 10, marginBottom: 12 },
  retakeBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#64748b', borderRadius: 8, paddingVertical: 8, paddingHorizontal: 16 },
  loadingCard: { backgroundColor: '#fff', borderRadius: 12, margin: 12, padding: 32, alignItems: 'center' },
})

const cam = StyleSheet.create({
  shutterOuter: { width: 72, height: 72, borderRadius: 36, borderWidth: 4, borderColor: '#fff', alignItems: 'center', justifyContent: 'center' },
  shutterInner: { width: 56, height: 56, borderRadius: 28, backgroundColor: '#fff' },
})

const rs = StyleSheet.create({
  confianceCard: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderRadius: 12, borderWidth: 1 },
  confianceTitre: { fontSize: 14, fontWeight: '700' },
  card: { backgroundColor: '#f8fafc', borderRadius: 12, borderWidth: 1, borderColor: '#e2e8f0', padding: 14 },
  cardTitle: { fontSize: 12, fontWeight: '700', color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  champRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  champKey: { fontSize: 12, color: '#64748b' },
  champVal: { fontSize: 12, fontWeight: '600', color: '#1e293b', flex: 1, textAlign: 'right' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 10, paddingVertical: 13 },
  actionText: { color: '#fff', fontWeight: '600', fontSize: 13 },
})
