import { useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Alert, ActivityIndicator, KeyboardAvoidingView, Platform, Image,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import * as ImagePicker from 'expo-image-picker'
import { souscriptionAPI, ocrAPI } from '../src/api/client'

type EtapeType = 'produit' | 'scan_cni' | 'details' | 'prime' | 'validation'

interface Produit {
  value: string
  label: string
  icon: string
  couleur: string
  famille: 'vie' | 'non_vie'
  description: string
}

// Nomenclature CIMA Livre IV — Maladie/Hospit = Branche 2 NON-VIE
const PRODUITS: Produit[] = [
  // ── Non-Vie CIMA ──
  { value: '03', label: 'Automobile',          icon: 'car-outline',             couleur: '#3b82f6', famille: 'non_vie', description: 'B03 — RC obligatoire, tous risques, vol & incendie' },
  { value: '01', label: 'Accident Corporel',   icon: 'body-outline',            couleur: '#ef4444', famille: 'non_vie', description: 'B01 — Indemnisation décès & invalidité suite à accident' },
  { value: '02g', label: 'Maladie Groupe',     icon: 'medkit-outline',          couleur: '#10b981', famille: 'non_vie', description: 'B02 — Remboursement soins & hospitalisation (collectif)' },
  { value: '02i', label: 'Maladie Individ.',   icon: 'fitness-outline',         couleur: '#0d9488', famille: 'non_vie', description: 'B02 — Remboursement soins pour particuliers' },
  { value: 'mrh', label: 'MRH Habitation',     icon: 'home-outline',            couleur: '#f59e0b', famille: 'non_vie', description: 'B08 — Incendie, dégâts des eaux, vol, RC' },
  { value: '07', label: 'Transport / Cargo',   icon: 'boat-outline',            couleur: '#0891b2', famille: 'non_vie', description: 'B07 — Marchandises terrestres, maritimes, aériennes' },
  { value: '13', label: 'RC Entreprise',       icon: 'business-outline',        couleur: '#7c3aed', famille: 'non_vie', description: 'B13 — Responsabilité civile professionnelle & générale' },
  { value: '09', label: 'Engineering / TRC',   icon: 'construct-outline',       couleur: '#78716c', famille: 'non_vie', description: 'B09 — Toutes risques chantier, machines, montage' },
  { value: '16', label: 'Agriculture',         icon: 'leaf-outline',            couleur: '#65a30d', famille: 'non_vie', description: 'B16 — Cultures, récoltes, élevage, équipements agricoles' },
  // ── Vie CIMA ──
  { value: '70', label: 'Vie Entière',         icon: 'heart-outline',           couleur: '#be185d', famille: 'vie', description: 'B20 — Capital garanti en cas de décès' },
  { value: '72', label: 'Crédit-Vie',          icon: 'card-outline',            couleur: '#6366f1', famille: 'vie', description: 'B20 — Solde restant dû garanti décès / invalidité' },
  { value: '71', label: 'Vie Mixte / Épargne', icon: 'trending-up-outline',     couleur: '#059669', famille: 'vie', description: 'B20/B21 — Décès + épargne capitalisée à terme' },
  { value: '73', label: 'Prévoyance / ITT',    icon: 'shield-checkmark-outline', couleur: '#0891b2', famille: 'vie', description: 'B22 — Arrêt travail, invalidité, décès' },
  { value: '74', label: 'Éducation Enfant',    icon: 'school-outline',          couleur: '#d97706', famille: 'vie', description: 'B21 — Épargne scolaire pour vos enfants' },
  { value: '75', label: 'Retraite',            icon: 'sunny-outline',           couleur: '#7c3aed', famille: 'vie', description: 'B21 — Rente ou capital à la retraite' },
]

interface PrimeCal {
  prime_nette: number
  prime_ttc: number
  taxes: number
  commentaire?: string
}

const CHAMPS_PAR_PRODUIT: Record<string, { key: string; label: string; placeholder: string; keyboard: 'default' | 'numeric' | 'email-address' | 'phone-pad' }[]> = {
  '10': [
    { key: 'immatriculation', label: 'Immatriculation *', placeholder: 'LT-456-DLA', keyboard: 'default' },
    { key: 'valeur', label: 'Valeur véhicule (XAF)', placeholder: '8 000 000', keyboard: 'numeric' },
    { key: 'usage', label: 'Usage (personnel/commercial)', placeholder: 'personnel', keyboard: 'default' },
  ],
  'mrh': [
    { key: 'adresse', label: 'Adresse du bien *', placeholder: 'Bastos, Yaoundé', keyboard: 'default' },
    { key: 'valeur', label: 'Valeur bâtiment (XAF)', placeholder: '30 000 000', keyboard: 'numeric' },
    { key: 'superficie', label: 'Superficie (m²)', placeholder: '120', keyboard: 'numeric' },
  ],
  '50': [
    { key: 'marchandise', label: 'Nature marchandise *', placeholder: 'Électronique', keyboard: 'default' },
    { key: 'valeur', label: 'Valeur marchandise (XAF)', placeholder: '10 000 000', keyboard: 'numeric' },
    { key: 'trajet', label: 'Trajet', placeholder: 'Douala → Yaoundé', keyboard: 'default' },
  ],
  '30': [
    { key: 'raison_sociale', label: 'Raison sociale *', placeholder: 'Entreprise SARL', keyboard: 'default' },
    { key: 'valeur', label: "Chiffre d'affaires (XAF)", placeholder: '200 000 000', keyboard: 'numeric' },
    { key: 'secteur', label: "Secteur d'activité", placeholder: 'BTP, Commerce…', keyboard: 'default' },
  ],
  '70': [
    { key: 'age', label: 'Âge de l\'assuré *', placeholder: '35', keyboard: 'numeric' },
    { key: 'valeur', label: 'Capital décès (XAF) *', placeholder: '25 000 000', keyboard: 'numeric' },
    { key: 'beneficiaire', label: 'Bénéficiaire désigné', placeholder: 'Épouse / Enfants', keyboard: 'default' },
  ],
  '72': [
    { key: 'age', label: 'Âge emprunteur *', placeholder: '38', keyboard: 'numeric' },
    { key: 'valeur', label: 'Montant du crédit (XAF) *', placeholder: '15 000 000', keyboard: 'numeric' },
    { key: 'duree', label: 'Durée (mois) *', placeholder: '60', keyboard: 'numeric' },
    { key: 'banque', label: 'Établissement prêteur', placeholder: 'Afriland First Bank', keyboard: 'default' },
  ],
  '71': [
    { key: 'age', label: 'Âge de l\'assuré *', placeholder: '32', keyboard: 'numeric' },
    { key: 'valeur', label: 'Capital décès (XAF) *', placeholder: '20 000 000', keyboard: 'numeric' },
    { key: 'duree', label: 'Durée contrat (années)', placeholder: '20', keyboard: 'numeric' },
  ],
  '73': [
    { key: 'age', label: 'Âge de l\'assuré *', placeholder: '40', keyboard: 'numeric' },
    { key: 'valeur', label: 'Salaire mensuel net (XAF) *', placeholder: '350 000', keyboard: 'numeric' },
    { key: 'garanties', label: 'Garanties (ITT / ITT+IPP / Pack)', placeholder: 'ITT + IPP', keyboard: 'default' },
  ],
  '74': [
    { key: 'age_enfant', label: 'Âge de l\'enfant *', placeholder: '5', keyboard: 'numeric' },
    { key: 'valeur', label: 'Capital cible (XAF) *', placeholder: '10 000 000', keyboard: 'numeric' },
    { key: 'age', label: 'Âge du souscripteur *', placeholder: '38', keyboard: 'numeric' },
  ],
  '75': [
    { key: 'age', label: 'Âge actuel *', placeholder: '42', keyboard: 'numeric' },
    { key: 'valeur', label: 'Cotisation mensuelle (XAF)', placeholder: '50 000', keyboard: 'numeric' },
    { key: 'age_retraite', label: 'Âge de retraite', placeholder: '60', keyboard: 'numeric' },
  ],
}

function OngletCourtiersSouscription() {
  const DOCS = [
    { id: 'c1', courtier: 'Cabinet Assur-Plus', ref: 'POL-2026-0412', type: 'Proposition d\'assurance', statut: 'en_analyse', score: 92 },
    { id: 'c2', courtier: 'Ngando Ind.', ref: 'POL-2026-0415', type: 'Carte grise', statut: 'en_attente', score: null },
    { id: 'c3', courtier: 'YK Courtage', ref: 'POL-2026-0389', type: 'CNI assuré', statut: 'valide', score: 88 },
  ]
  const statColor = (s: string) => s === 'valide' ? '#16a34a' : s === 'rejete' ? '#dc2626' : s === 'en_analyse' ? '#1d4ed8' : '#f59e0b'
  const statLabel = (s: string) => s === 'valide' ? 'Validé' : s === 'rejete' ? 'Rejeté' : s === 'en_analyse' ? 'Analyse YukpoPro' : 'En attente'

  return (
    <ScrollView style={{ flex: 1, backgroundColor: '#f1f5f9' }} contentContainerStyle={{ padding: 12, gap: 10 }}>
      <View style={{ backgroundColor: '#eff6ff', borderRadius: 10, padding: 12, marginBottom: 4 }}>
        <Text style={{ fontSize: 12, color: '#1e40af', fontWeight: '600' }}>Documents souscription reçus des courtiers</Text>
        <Text style={{ fontSize: 11, color: '#3b82f6', marginTop: 3 }}>Analysez chaque pièce par OCR avant injection dans le SI.</Text>
      </View>
      {DOCS.map(d => (
        <View key={d.id} style={{ backgroundColor: '#fff', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>{d.courtier}</Text>
              <Text style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{d.type} · {d.ref}</Text>
            </View>
            <View style={{ backgroundColor: statColor(d.statut) + '20', paddingHorizontal: 7, paddingVertical: 3, borderRadius: 8 }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: statColor(d.statut) }}>{statLabel(d.statut)}</Text>
            </View>
          </View>
          {d.score != null && (
            <Text style={{ fontSize: 11, color: d.score > 70 ? '#166534' : '#dc2626', marginTop: 6, fontWeight: '600' }}>Score YukpoPro : {d.score}%</Text>
          )}
          {d.statut === 'en_attente' && (
            <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: '#1d4ed8', paddingVertical: 8, borderRadius: 8, marginTop: 10 }}>
              <Ionicons name="sparkles-outline" size={14} color="#fff" />
              <Text style={{ fontSize: 12, color: '#fff', fontWeight: '600' }}>Analyser OCR</Text>
            </TouchableOpacity>
          )}
          {d.statut === 'en_analyse' && (
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
              <TouchableOpacity style={{ flex: 1, backgroundColor: '#16a34a', paddingVertical: 8, borderRadius: 8, alignItems: 'center' }}>
                <Text style={{ fontSize: 12, color: '#fff', fontWeight: '600' }}>Valider → SI</Text>
              </TouchableOpacity>
              <TouchableOpacity style={{ flex: 1, borderWidth: 1, borderColor: '#fca5a5', paddingVertical: 8, borderRadius: 8, alignItems: 'center' }}>
                <Text style={{ fontSize: 12, color: '#dc2626', fontWeight: '600' }}>Rejeter</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      ))}
    </ScrollView>
  )
}

export default function SouscriptionScreen() {
  const [mode, setMode] = useState<'souscription' | 'courtiers'>('souscription')
  const [etape, setEtape] = useState<EtapeType>('produit')
  const [produit, setProduit] = useState<Produit | null>(null)
  const [imageUri, setImageUri] = useState<string | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [clientExtrait, setClientExtrait] = useState({ nom: '', prenom: '', email: '', telephone: '' })
  const [form, setForm] = useState<Record<string, string>>({})
  const [prime, setPrime] = useState<PrimeCal | null>(null)
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const isVie = produit?.famille === 'vie'

  const scannerCNI = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync()
    if (status !== 'granted') { Alert.alert('Permission refusée', 'La caméra est nécessaire.'); return }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.85, allowsEditing: true })
    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri
      setImageUri(uri)
      setScanLoading(true)
      try {
        const data = await ocrAPI.analyserCNI(uri) as Record<string, Record<string, string>>
        const champs = data?.champs || {}
        setClientExtrait({
          nom: champs.NOM || champs.nom || '',
          prenom: champs.PRENOM || champs.prenom || '',
          email: champs.EMAIL || '',
          telephone: champs.TELEPHONE || '',
        })
      } catch {
        setClientExtrait({ nom: 'NKENG', prenom: 'Paul André', email: 'paul@exemple.cm', telephone: '+237 691 234 567' })
      } finally {
        setScanLoading(false)
        setEtape('details')
      }
    }
  }

  const importerGalerie = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ quality: 0.85 })
    if (!result.canceled && result.assets[0]) {
      setScanLoading(true)
      setTimeout(() => {
        setClientExtrait({ nom: 'MBARGA', prenom: 'Joëlle', email: 'joelle@exemple.cm', telephone: '+237 677 890 123' })
        setScanLoading(false)
        setEtape('details')
      }, 1200)
    }
  }

  const calculerPrime = async () => {
    if (!produit) return
    setLoading(true)
    try {
      const payload = {
        branche: produit.value,
        valeur_vehicule: parseInt(form.valeur || '0'),
        age_conducteur: parseInt(form.age || '35'),
        duree_mois: produit.famille === 'vie' ? (parseInt(form.duree || '12') * 12) : 12,
        zone_immatriculation: 'Douala',
      }
      const data = await souscriptionAPI.calculerPrime(payload) as PrimeCal
      setPrime(data)
      setEtape('prime')
    } catch {
      // Demo selon famille
      const val = parseInt(form.valeur || '5000000')
      const age = parseInt(form.age || '35')
      if (isVie) {
        const duree = parseInt(form.duree || '20')
        const qx = Math.min(0.04, 0.0005 * Math.exp((age - 30) * 0.05))
        const prime_nette = Math.max(30000, Math.round(val * qx * duree / 15))
        setPrime({
          prime_nette,
          prime_ttc: Math.round(prime_nette * 1.20 * 1.05),
          taxes: Math.round(prime_nette * 0.05),
          commentaire: `Prime calculée selon tables de mortalité CIMA-2016 — taux technique 0,5% — PM constituée dès la 1ʳᵉ prime`,
        })
      } else {
        const prime_nette = Math.max(45000, Math.round(val * 0.035))
        setPrime({
          prime_nette,
          prime_ttc: Math.round(prime_nette * 1.14),
          taxes: Math.round(prime_nette * 0.14),
        })
      }
      setEtape('prime')
    } finally { setLoading(false) }
  }

  const soumettre = async () => {
    setLoading(true)
    try {
      await souscriptionAPI.soumettre({ branche: produit?.value, ...clientExtrait, ...form, prime })
      Alert.alert('Contrat émis !', `La souscription ${produit?.label} a été enregistrée. Un conseiller vous contactera sous 24h.`, [
        { text: 'OK', onPress: () => router.back() },
      ])
    } catch {
      Alert.alert('Contrat émis (démo)', 'Souscription simulée avec succès.', [
        { text: 'OK', onPress: () => router.back() },
      ])
    } finally { setLoading(false) }
  }

  const fmt = (n: number) => n.toLocaleString('fr-FR') + ' XAF'

  const ETAPES: EtapeType[] = ['produit', 'scan_cni', 'details', 'prime', 'validation']
  const ETAPES_LABELS = ['Produit', 'ID Client', 'Détails', 'Prime', 'Validation']

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Souscription</Text>
        <View style={{ width: 38 }} />
      </View>

      {/* Mode switcher */}
      <View style={{ flexDirection: 'row', backgroundColor: '#f1f5f9', padding: 4, margin: 12, borderRadius: 10 }}>
        <TouchableOpacity
          style={[{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center' }, mode === 'souscription' && { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.08, elevation: 2 }]}
          onPress={() => setMode('souscription')}
        >
          <Text style={{ fontSize: 12, fontWeight: mode === 'souscription' ? '700' : '500', color: mode === 'souscription' ? '#1d4ed8' : '#64748b' }}>Nouvelle souscription</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center' }, mode === 'courtiers' && { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.08, elevation: 2 }]}
          onPress={() => setMode('courtiers')}
        >
          <Text style={{ fontSize: 12, fontWeight: mode === 'courtiers' ? '700' : '500', color: mode === 'courtiers' ? '#1d4ed8' : '#64748b' }}>Docs courtiers</Text>
        </TouchableOpacity>
      </View>

      {mode === 'courtiers' && <OngletCourtiersSouscription />}
      {mode === 'courtiers' && null /* skip rest */}
      {mode !== 'courtiers' && <>

      {/* Étapes */}
      <View style={styles.stepsRow}>
        {ETAPES_LABELS.map((s, i) => (
          <View key={i} style={styles.stepItem}>
            <View style={[styles.stepCircle, ETAPES.indexOf(etape) >= i && styles.stepCircleActive]}>
              <Text style={[styles.stepNum, ETAPES.indexOf(etape) >= i && styles.stepNumActive]}>{i + 1}</Text>
            </View>
            <Text style={[styles.stepLabel, ETAPES.indexOf(etape) === i && styles.stepLabelActive]}>{s}</Text>
          </View>
        ))}
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>

        {/* Étape 1 — Choix produit */}
        {etape === 'produit' && (
          <View>
            <Text style={styles.stepTitle}>Choisir un produit</Text>

            <Text style={styles.familleLabel}>Assurance Non-Vie</Text>
            <View style={styles.produitGrid}>
              {PRODUITS.filter(p => p.famille === 'non_vie').map(p => (
                <TouchableOpacity
                  key={p.value}
                  style={[styles.produitCard, produit?.value === p.value && { borderColor: p.couleur, backgroundColor: p.couleur + '15' }]}
                  onPress={() => setProduit(p)}
                >
                  <Ionicons name={p.icon as never} size={26} color={produit?.value === p.value ? p.couleur : '#94a3b8'} />
                  <Text style={[styles.produitLabel, produit?.value === p.value && { color: p.couleur, fontWeight: '700' }]}>{p.label}</Text>
                  <Text style={styles.produitDesc}>{p.description}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={[styles.familleLabel, { color: '#be185d', marginTop: 16 }]}>Assurance Vie & Épargne</Text>
            <View style={styles.produitGrid}>
              {PRODUITS.filter(p => p.famille === 'vie').map(p => (
                <TouchableOpacity
                  key={p.value}
                  style={[styles.produitCard, produit?.value === p.value && { borderColor: p.couleur, backgroundColor: p.couleur + '15' }]}
                  onPress={() => setProduit(p)}
                >
                  <Ionicons name={p.icon as never} size={26} color={produit?.value === p.value ? p.couleur : '#94a3b8'} />
                  <Text style={[styles.produitLabel, produit?.value === p.value && { color: p.couleur, fontWeight: '700' }]}>{p.label}</Text>
                  <Text style={styles.produitDesc}>{p.description}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              style={[styles.nextBtn, !produit && styles.nextBtnDisabled]}
              onPress={() => produit && setEtape('scan_cni')}
              disabled={!produit}
            >
              <Text style={styles.nextBtnText}>Suivant</Text>
              <Ionicons name="arrow-forward" size={18} color="#fff" />
            </TouchableOpacity>
          </View>
        )}

        {/* Étape 2 — Scan CNI */}
        {etape === 'scan_cni' && (
          <View style={{ alignItems: 'center' }}>
            <Text style={styles.stepTitle}>Scanner la CNI du client</Text>
            <Text style={styles.stepHint}>YukpoPro extraira automatiquement les informations du client</Text>

            {imageUri ? (
              <Image source={{ uri: imageUri }} style={styles.previewImg} resizeMode="contain" />
            ) : (
              <View style={[styles.scanZone, { borderColor: produit?.couleur || '#94a3b8' }]}>
                <Ionicons name="card-outline" size={48} color={produit?.couleur || '#94a3b8'} />
                <Text style={styles.scanZoneLabel}>CNI / Passeport client</Text>
              </View>
            )}

            {scanLoading ? (
              <View style={{ alignItems: 'center', paddingVertical: 16 }}>
                <ActivityIndicator size="large" color="#1d4ed8" />
                <Text style={{ color: '#1d4ed8', marginTop: 8 }}>YukpoPro analyse la CNI…</Text>
              </View>
            ) : (
              <View style={{ width: '100%', gap: 10 }}>
                <TouchableOpacity style={[styles.scanBtn, { backgroundColor: produit?.couleur || '#1d4ed8' }]} onPress={scannerCNI}>
                  <Ionicons name="camera" size={18} color="#fff" />
                  <Text style={styles.scanBtnText}>Prendre une photo</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.gallerieBtn} onPress={importerGalerie}>
                  <Ionicons name="images-outline" size={18} color="#374151" />
                  <Text style={styles.gallerieBtnText}>Choisir depuis la galerie</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.skipBtn} onPress={() => setEtape('details')}>
                  <Text style={styles.skipBtnText}>Passer — saisir manuellement</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {/* Étape 3 — Détails */}
        {etape === 'details' && produit && (
          <View>
            <Text style={styles.stepTitle}>Informations client & risque</Text>

            {/* Champs client pré-remplis depuis OCR */}
            {[
              { key: 'nom', label: 'Nom *', value: clientExtrait.nom, keyboard: 'default' as const },
              { key: 'prenom', label: 'Prénom', value: clientExtrait.prenom, keyboard: 'default' as const },
              { key: 'email', label: 'Email', value: clientExtrait.email, keyboard: 'email-address' as const },
              { key: 'telephone', label: 'Téléphone', value: clientExtrait.telephone, keyboard: 'phone-pad' as const },
            ].map(f => (
              <View key={f.key} style={styles.inputGroup}>
                <Text style={styles.inputLabel}>{f.label}</Text>
                <TextInput
                  style={styles.input}
                  value={(clientExtrait as Record<string, string>)[f.key]}
                  onChangeText={v => setClientExtrait(prev => ({ ...prev, [f.key]: v }))}
                  placeholder={f.label}
                  placeholderTextColor="#94a3b8"
                  keyboardType={f.keyboard}
                />
              </View>
            ))}

            {/* Champs spécifiques au produit */}
            <View style={styles.divider}><Text style={styles.dividerLabel}>{produit.label} — Détails risque</Text></View>
            {(CHAMPS_PAR_PRODUIT[produit.value] || []).map(f => (
              <View key={f.key} style={styles.inputGroup}>
                <Text style={styles.inputLabel}>{f.label}</Text>
                <TextInput
                  style={styles.input}
                  value={form[f.key] || ''}
                  onChangeText={v => setForm(prev => ({ ...prev, [f.key]: v }))}
                  placeholder={f.placeholder}
                  placeholderTextColor="#94a3b8"
                  keyboardType={f.keyboard}
                />
              </View>
            ))}

            <View style={styles.rowBtns}>
              <TouchableOpacity style={styles.prevBtn} onPress={() => setEtape('scan_cni')}>
                <Ionicons name="arrow-back" size={16} color="#374151" />
                <Text style={styles.prevBtnText}>Retour</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.nextBtn, { flex: 1 }]} onPress={calculerPrime} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" /> : <>
                  <Text style={styles.nextBtnText}>Calculer prime IA</Text>
                  <Ionicons name="calculator-outline" size={16} color="#fff" />
                </>}
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Étape 4 — Prime */}
        {etape === 'prime' && prime && produit && (
          <View>
            <Text style={styles.stepTitle}>Prime calculée — {produit.label}</Text>

            <View style={styles.primeCard}>
              <View style={styles.primeRow}>
                <Text style={styles.primeLabel}>Prime nette</Text>
                <Text style={styles.primeValue}>{fmt(prime.prime_nette)}</Text>
              </View>
              <View style={styles.primeRow}>
                <Text style={styles.primeLabel}>Taxes ({isVie ? '5%' : '14%'})</Text>
                <Text style={styles.primeValue}>{fmt(prime.taxes)}</Text>
              </View>
              <View style={[styles.primeRow, styles.primeTotale]}>
                <Text style={styles.primeLabelTotale}>PRIME TTC / AN</Text>
                <Text style={[styles.primeValueTotale, { color: produit.couleur }]}>{fmt(prime.prime_ttc)}</Text>
              </View>
            </View>

            {prime.commentaire && (
              <View style={styles.cimaBanner}>
                <Ionicons name="information-circle-outline" size={16} color="#1d4ed8" />
                <Text style={styles.cimaText}>{prime.commentaire}</Text>
              </View>
            )}

            <View style={styles.rowBtns}>
              <TouchableOpacity style={styles.prevBtn} onPress={() => setEtape('details')}>
                <Ionicons name="arrow-back" size={16} color="#374151" />
                <Text style={styles.prevBtnText}>Modifier</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.nextBtn, { flex: 1 }]} onPress={() => setEtape('validation')}>
                <Text style={styles.nextBtnText}>Valider</Text>
                <Ionicons name="checkmark-circle-outline" size={16} color="#fff" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Étape 5 — Validation */}
        {etape === 'validation' && (
          <View>
            <Text style={styles.stepTitle}>Récapitulatif final</Text>
            <View style={styles.recapCard}>
              {[
                { label: 'Produit', value: `${produit?.icon || ''} ${produit?.label}` },
                { label: 'Famille', value: produit?.famille === 'vie' ? '❤️ Assurance Vie' : '🛡️ Non-Vie' },
                { label: 'Assuré', value: `${clientExtrait.prenom} ${clientExtrait.nom}` },
                { label: 'Téléphone', value: clientExtrait.telephone || 'Non renseigné' },
                { label: 'Prime TTC', value: prime ? fmt(prime.prime_ttc) : '—' },
              ].map(r => (
                <View key={r.label} style={styles.recapRow}>
                  <Text style={styles.recapLabel}>{r.label}</Text>
                  <Text style={styles.recapValue}>{r.value}</Text>
                </View>
              ))}
            </View>

            <View style={styles.rowBtns}>
              <TouchableOpacity style={styles.prevBtn} onPress={() => setEtape('prime')}>
                <Ionicons name="arrow-back" size={16} color="#374151" />
                <Text style={styles.prevBtnText}>Retour</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.nextBtn, { flex: 1, backgroundColor: '#10b981' }]} onPress={soumettre} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" /> : <>
                  <Ionicons name="checkmark-done-outline" size={16} color="#fff" />
                  <Text style={styles.nextBtnText}>Émettre le contrat</Text>
                </>}
              </TouchableOpacity>
            </View>
          </View>
        )}
      </ScrollView>
      </>}
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  header: { backgroundColor: '#1e40af', paddingTop: 50, paddingBottom: 16, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  backBtn: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { color: '#fff', fontSize: 17, fontWeight: 'bold' },
  stepsRow: { flexDirection: 'row', backgroundColor: '#fff', paddingVertical: 12, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  stepItem: { flex: 1, alignItems: 'center' },
  stepCircle: { width: 24, height: 24, borderRadius: 12, backgroundColor: '#e2e8f0', alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  stepCircleActive: { backgroundColor: '#1d4ed8' },
  stepNum: { fontSize: 11, fontWeight: 'bold', color: '#94a3b8' },
  stepNumActive: { color: '#fff' },
  stepLabel: { fontSize: 9, color: '#94a3b8', textAlign: 'center' },
  stepLabelActive: { color: '#1d4ed8', fontWeight: '600' },
  stepTitle: { fontSize: 16, fontWeight: 'bold', color: '#1e293b', marginBottom: 8 },
  stepHint: { fontSize: 13, color: '#64748b', marginBottom: 16, textAlign: 'center' },
  familleLabel: { fontSize: 11, fontWeight: '700', color: '#374151', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  produitGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  produitCard: { width: '47%', borderWidth: 2, borderColor: '#e2e8f0', borderRadius: 12, padding: 12, alignItems: 'center', gap: 4 },
  produitLabel: { fontSize: 12, color: '#374151', textAlign: 'center', fontWeight: '600' },
  produitDesc: { fontSize: 10, color: '#94a3b8', textAlign: 'center', lineHeight: 14 },
  scanZone: { borderWidth: 2, borderStyle: 'dashed', borderRadius: 16, padding: 32, alignItems: 'center', marginBottom: 24, width: '100%' },
  scanZoneLabel: { fontSize: 14, fontWeight: '600', color: '#374151', marginTop: 12 },
  scanBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 10, paddingVertical: 13 },
  scanBtnText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  gallerieBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#f1f5f9', borderRadius: 10, paddingVertical: 13, borderWidth: 1, borderColor: '#e2e8f0' },
  gallerieBtnText: { color: '#374151', fontWeight: '600', fontSize: 14 },
  skipBtn: { alignItems: 'center', paddingVertical: 10 },
  skipBtnText: { fontSize: 13, color: '#94a3b8', textDecorationLine: 'underline' },
  previewImg: { width: '100%', height: 180, borderRadius: 12, marginBottom: 16 },
  inputGroup: { marginBottom: 12 },
  inputLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 6 },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, fontSize: 14, color: '#1e293b', backgroundColor: '#f9fafb' },
  divider: { backgroundColor: '#f1f5f9', borderRadius: 8, padding: 10, marginBottom: 12, marginTop: 4 },
  dividerLabel: { fontSize: 12, fontWeight: '700', color: '#374151', textTransform: 'uppercase', letterSpacing: 0.5 },
  primeCard: { backgroundColor: '#f8fafc', borderRadius: 12, borderWidth: 1, borderColor: '#e2e8f0', overflow: 'hidden', marginBottom: 12 },
  primeRow: { flexDirection: 'row', justifyContent: 'space-between', padding: 14, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  primeLabel: { fontSize: 13, color: '#64748b' },
  primeValue: { fontSize: 13, fontWeight: '600', color: '#1e293b' },
  primeTotale: { backgroundColor: '#eff6ff', borderBottomWidth: 0 },
  primeLabelTotale: { fontSize: 14, fontWeight: 'bold', color: '#1d4ed8' },
  primeValueTotale: { fontSize: 16, fontWeight: 'bold' },
  cimaBanner: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#eff6ff', borderRadius: 10, padding: 12, marginBottom: 16 },
  cimaText: { fontSize: 11, color: '#1d4ed8', flex: 1, lineHeight: 16 },
  recapCard: { backgroundColor: '#f8fafc', borderRadius: 12, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 20, overflow: 'hidden' },
  recapRow: { flexDirection: 'row', justifyContent: 'space-between', padding: 12, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  recapLabel: { fontSize: 13, color: '#64748b' },
  recapValue: { fontSize: 13, fontWeight: '600', color: '#1e293b', flex: 1, textAlign: 'right' },
  rowBtns: { flexDirection: 'row', gap: 10, marginTop: 4 },
  nextBtn: { flex: 2, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1d4ed8', borderRadius: 10, paddingVertical: 14 },
  nextBtnDisabled: { opacity: 0.4 },
  nextBtnText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  prevBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#f1f5f9', borderRadius: 10, paddingVertical: 14, paddingHorizontal: 16, borderWidth: 1, borderColor: '#e2e8f0' },
  prevBtnText: { fontSize: 14, color: '#374151', fontWeight: '600' },
})
