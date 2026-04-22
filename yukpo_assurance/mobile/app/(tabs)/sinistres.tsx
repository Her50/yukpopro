import { useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, RefreshControl, Modal, Alert, ActivityIndicator,
  Image, KeyboardAvoidingView, Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import * as ImagePicker from 'expo-image-picker'
import { sinistresAPI, ocrAPI, apiClient } from '../../src/api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

type OngletType = 'dossiers' | 'recours' | 'lettres' | 'fournisseurs' | 'courtiers'

interface Sinistre {
  id: string; numero: string; assure: string; branche: string
  branche_cima: string; date_sinistre: string; montant_evalue: number
  statut: string; score_fraude: number; compte_charge: string
}

interface Recours {
  id: string; numero: string; sinistre_ref: string; tiers: string
  type: string; montant_reclame: number; montant_obtenu?: number; statut: string
}

// ─── Données démo ─────────────────────────────────────────────────────────────

// Nomenclature CIMA Livre IV — Hospitalisation/Maladie = Branche 2 NON-VIE
const BRANCHES_CFG: Record<string, { cima: string; charge: string; famille: 'vie' | 'non_vie'; couleur: string }> = {
  'Automobile':            { cima: 'B03 — RC/Corps Auto', charge: '6141', famille: 'non_vie', couleur: '#3b82f6' },
  'Accident Corporel':     { cima: 'B01 — Accidents corp.', charge: '6140', famille: 'non_vie', couleur: '#ef4444' },
  'Maladie / Hospit.':     { cima: 'B02 — Maladie (Non-Vie)', charge: '6144', famille: 'non_vie', couleur: '#10b981' },
  'MRH / Incendie':        { cima: 'B08 — Incendie/IRD', charge: '6142', famille: 'non_vie', couleur: '#f59e0b' },
  'Transport':             { cima: 'B07 — Marchandises', charge: '6145', famille: 'non_vie', couleur: '#0891b2' },
  'RC Entreprise':         { cima: 'B13 — RC Générale', charge: '6143', famille: 'non_vie', couleur: '#7c3aed' },
  'Engineering / TRC':     { cima: 'B09 — Dommages biens', charge: '6146', famille: 'non_vie', couleur: '#78716c' },
  'Agriculture':           { cima: 'B16 — Agriculture', charge: '6147', famille: 'non_vie', couleur: '#65a30d' },
  'Vie — Décès':           { cima: 'B20 — Assurance Vie', charge: '6171', famille: 'vie',     couleur: '#be185d' },
  'Vie — IPP/Invalidité':  { cima: 'B22 — Rente/Invalidité', charge: '6172', famille: 'vie',     couleur: '#9333ea' },
  'Vie — ITT':             { cima: 'B22 — Prévoyance ITT', charge: '6173', famille: 'vie',     couleur: '#d97706' },
  'Vie — Épargne/Capital': { cima: 'B21 — Capitalisation', charge: '6174', famille: 'vie',     couleur: '#0d9488' },
}

const SINISTRES_DEMO: Sinistre[] = [
  { id: '1', numero: 'SIN-2026-0234', assure: 'NKENG Paul', branche: 'Automobile', branche_cima: 'B10', date_sinistre: '2026-03-10', montant_evalue: 3685000, statut: 'en_instruction', score_fraude: 12, compte_charge: '6141' },
  { id: '2', numero: 'SIN-2026-0235', assure: 'TRAORÉ Aminata', branche: 'Vie — Décès', branche_cima: 'B70', date_sinistre: '2026-03-08', montant_evalue: 25000000, statut: 'en_instruction', score_fraude: 5, compte_charge: '6171' },
  { id: '3', numero: 'SIN-2026-0198', assure: 'MBARGA Joëlle', branche: 'Maladie / Hospit.', branche_cima: 'B02', date_sinistre: '2026-03-08', montant_evalue: 1250000, statut: 'accepte', score_fraude: 8, compte_charge: '6144' },
  { id: '4', numero: 'SIN-2026-0276', assure: 'FOGUE Henri', branche: 'Automobile', branche_cima: 'B10', date_sinistre: '2026-03-12', montant_evalue: 850000, statut: 'en_attente', score_fraude: 34, compte_charge: '6141' },
  { id: '5', numero: 'SIN-2026-0289', assure: 'KOUASSI A.', branche: 'MRH / Incendie', branche_cima: 'B20', date_sinistre: '2026-03-15', montant_evalue: 15200000, statut: 'expertise', score_fraude: 72, compte_charge: '6142' },
  { id: '6', numero: 'SIN-2026-0301', assure: 'DIALLO Fatou', branche: 'Vie — IPP', branche_cima: 'B73', date_sinistre: '2026-03-18', montant_evalue: 5000000, statut: 'regle', score_fraude: 5, compte_charge: '6172' },
]

const RECOURS_DEMO: Recours[] = [
  { id: '1', numero: 'REC-2026-001', sinistre_ref: 'SIN-2026-0234', tiers: 'Assureur tiers Allianz', type: 'Subrogatoire', montant_reclame: 2500000, statut: 'en_cours' },
  { id: '2', numero: 'REC-2026-002', sinistre_ref: 'SIN-2026-0289', tiers: 'AXA CI (co-assureur 30%)', type: 'Contribution', montant_reclame: 3600000, montant_obtenu: 3600000, statut: 'obtenu' },
]

const TEMPLATES_LETTRES = [
  { id: 'accuse', label: 'Accusé de réception', icon: 'mail-outline' as const },
  { id: 'demande_pieces', label: 'Demande de pièces', icon: 'document-text-outline' as const },
  { id: 'notification_reglement', label: 'Notification de règlement', icon: 'checkmark-circle-outline' as const },
  { id: 'rejet', label: 'Lettre de rejet', icon: 'close-circle-outline' as const },
  { id: 'expertise', label: 'Convocation expertise', icon: 'search-outline' as const },
  { id: 'mise_demeure', label: 'Mise en demeure (recours)', icon: 'warning-outline' as const },
]

// Branche 2 CIMA = Maladie → Non-Vie (pas Vie)
const TYPES_SINISTRE_DECL = [
  // ── Non-Vie ──
  { value: 'auto',      label: 'Automobile',         icon: 'car-outline' as const,              couleur: '#3b82f6', famille: 'non_vie', branche_cima: 'B03' },
  { value: 'accident',  label: 'Accident Corporel',  icon: 'body-outline' as const,             couleur: '#ef4444', famille: 'non_vie', branche_cima: 'B01' },
  { value: 'maladie',   label: 'Maladie / Hospit.',  icon: 'medkit-outline' as const,           couleur: '#10b981', famille: 'non_vie', branche_cima: 'B02' },
  { value: 'mrh',       label: 'MRH / Incendie',     icon: 'home-outline' as const,             couleur: '#f59e0b', famille: 'non_vie', branche_cima: 'B08' },
  { value: 'transport', label: 'Transport',           icon: 'boat-outline' as const,             couleur: '#0891b2', famille: 'non_vie', branche_cima: 'B07' },
  { value: 'rc',        label: 'RC Entreprise',       icon: 'business-outline' as const,         couleur: '#7c3aed', famille: 'non_vie', branche_cima: 'B13' },
  { value: 'engineering',label: 'Engineering/TRC',   icon: 'construct-outline' as const,        couleur: '#78716c', famille: 'non_vie', branche_cima: 'B09' },
  { value: 'agriculture',label: 'Agriculture',        icon: 'leaf-outline' as const,             couleur: '#65a30d', famille: 'non_vie', branche_cima: 'B16' },
  // ── Vie ──
  { value: 'deces',     label: 'Décès (Vie)',         icon: 'heart-outline' as const,            couleur: '#be185d', famille: 'vie',     branche_cima: 'B20' },
  { value: 'invalidite',label: 'Invalidité / IPP',    icon: 'accessibility-outline' as const,    couleur: '#9333ea', famille: 'vie',     branche_cima: 'B22' },
  { value: 'itt',       label: 'Arrêt travail ITT',   icon: 'bandage-outline' as const,          couleur: '#d97706', famille: 'vie',     branche_cima: 'B22' },
  { value: 'epargne',   label: 'Épargne / Capital',   icon: 'trending-up-outline' as const,      couleur: '#0d9488', famille: 'vie',     branche_cima: 'B21' },
]

const STATUT_CFG: Record<string, { label: string; bg: string; text: string }> = {
  en_attente:    { label: 'En attente', bg: '#fef3c7', text: '#92400e' },
  en_instruction:{ label: 'En instruction', bg: '#dbeafe', text: '#1e40af' },
  expertise:     { label: 'Expertise', bg: '#f3e8ff', text: '#6b21a8' },
  accepte:       { label: 'Accepté', bg: '#dcfce7', text: '#14532d' },
  regle:         { label: 'Réglé', bg: '#d1fae5', text: '#065f46' },
  rejete:        { label: 'Rejeté', bg: '#fee2e2', text: '#7f1d1d' },
}

// ─── Onglet Dossiers ──────────────────────────────────────────────────────────

function OngletDossiers() {
  const [sinistres, setSinistres] = useState<Sinistre[]>(SINISTRES_DEMO)
  const [recherche, setRecherche] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [filtreFamille, setFiltreFamille] = useState<'tous' | 'vie' | 'non_vie'>('tous')
  const [selected, setSelected] = useState<Sinistre | null>(null)
  const [declarerVisible, setDeclarerVisible] = useState(false)
  const [etapeDecl, setEtapeDecl] = useState<'type' | 'scan' | 'validation' | 'succes'>('type')
  const [typeChoisi, setTypeChoisi] = useState<typeof TYPES_SINISTRE_DECL[0] | null>(null)
  const [imageUri, setImageUri] = useState<string | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [champsExtraits, setChampsExtraits] = useState<{ label: string; valeur: string }[]>([])
  const [submitLoading, setSubmitLoading] = useState(false)

  const onRefresh = async () => {
    setRefreshing(true)
    try {
      const data = await sinistresAPI.list() as Record<string, unknown>
      if (Array.isArray(data?.items)) setSinistres(data.items as Sinistre[])
    } catch {} finally { setRefreshing(false) }
  }

  const filtres = sinistres.filter(s => {
    const matchRecherche = s.assure.toLowerCase().includes(recherche.toLowerCase()) || s.numero.includes(recherche)
    const matchFamille = filtreFamille === 'tous' ||
      (filtreFamille === 'vie' && (BRANCHES_CFG[s.branche]?.famille === 'vie')) ||
      (filtreFamille === 'non_vie' && BRANCHES_CFG[s.branche]?.famille === 'non_vie')
    return matchRecherche && matchFamille
  })

  const fraudeCouleur = (score: number) => score < 30 ? '#16a34a' : score < 60 ? '#d97706' : '#dc2626'

  const scannerDocument = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync()
    if (status !== 'granted') { Alert.alert('Permission refusée', 'La caméra est nécessaire.'); return }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.85, allowsEditing: true })
    if (!result.canceled && result.assets[0]) {
      setImageUri(result.assets[0].uri)
      setScanLoading(true)
      try {
        const data = await ocrAPI.analyserImage(result.assets[0].uri, typeChoisi?.value || 'document') as Record<string, unknown>
        const champs = Object.entries((data.champs as Record<string, string>) || {})
          .map(([k, v]) => ({ label: k.replace(/_/g, ' '), valeur: v }))
        setChampsExtraits(champs.length > 0 ? champs : demoChamps(typeChoisi?.value || 'auto'))
      } catch { setChampsExtraits(demoChamps(typeChoisi?.value || 'auto')) }
      finally { setScanLoading(false); setEtapeDecl('validation') }
    }
  }

  const demoChamps = (type: string) => {
    const demos: Record<string, { label: string; valeur: string }[]> = {
      auto: [{ label: 'Assuré', valeur: 'NKENG Paul André' }, { label: 'N° police', valeur: 'POL-AUTO-2026-001' }, { label: 'Immatriculation', valeur: 'LT-456-DLA' }, { label: 'Date sinistre', valeur: new Date().toLocaleDateString('fr-FR') }, { label: 'Montant estimé', valeur: '850 000 XAF' }],
      deces: [{ label: 'Assuré décédé', valeur: 'TRAORÉ Ibrahim' }, { label: 'N° police vie', valeur: 'CTR-VIE-2025-018' }, { label: 'Capital décès', valeur: '25 000 000 XAF' }, { label: 'Date décès', valeur: new Date().toLocaleDateString('fr-FR') }, { label: 'Bénéficiaire', valeur: 'TRAORÉ Aminata (épouse)' }],
      hospitalisation: [{ label: 'Assuré', valeur: 'OUÉDRAOGO Marie' }, { label: 'Établissement', valeur: 'Clinique Saint-Luc' }, { label: 'Durée séjour', valeur: '5 jours' }, { label: 'Total facturé', valeur: '1 250 000 XAF' }, { label: 'Remboursable', valeur: '720 000 XAF' }],
    }
    return demos[type] || demos.auto
  }

  const soumettreSinistre = async () => {
    setSubmitLoading(true)
    await new Promise(r => setTimeout(r, 1000))
    const cfg = BRANCHES_CFG[typeChoisi?.label || ''] || { cima: 'B10', charge: '6141', famille: 'non_vie' as const, couleur: '#3b82f6' }
    const nouveau: Sinistre = {
      id: Date.now().toString(),
      numero: `SIN-2026-${String(sinistres.length + 300).padStart(4, '0')}`,
      assure: champsExtraits.find(c => c.label.toLowerCase().includes('assuré'))?.valeur || 'Nouveau assuré',
      branche: typeChoisi?.label || 'Automobile',
      branche_cima: typeChoisi?.branche_cima || 'B10',
      date_sinistre: new Date().toISOString().slice(0, 10),
      montant_evalue: parseInt((champsExtraits.find(c => c.label.toLowerCase().includes('montant'))?.valeur || '500000').replace(/\D/g, '')) || 500000,
      statut: 'en_attente',
      score_fraude: Math.floor(Math.random() * 20),
      compte_charge: cfg.charge,
    }
    setSinistres(prev => [nouveau, ...prev])
    setSubmitLoading(false)
    setEtapeDecl('succes')
  }

  const resetDecl = () => {
    setDeclarerVisible(false); setEtapeDecl('type'); setTypeChoisi(null)
    setImageUri(null); setChampsExtraits([])
  }

  return (
    <View style={{ flex: 1 }}>
      {/* Barre recherche + Déclarer */}
      <View style={styles.topBar}>
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={16} color="#94a3b8" style={{ marginRight: 6 }} />
          <TextInput style={styles.searchInput} value={recherche} onChangeText={setRecherche} placeholder="Rechercher…" placeholderTextColor="#94a3b8" />
        </View>
        <TouchableOpacity style={styles.declarerBtn} onPress={() => setDeclarerVisible(true)}>
          <Ionicons name="camera" size={16} color="#fff" />
          <Text style={styles.declarerBtnText}>Déclarer</Text>
        </TouchableOpacity>
      </View>

      {/* Filtre famille + branch codes */}
      <View style={styles.filtreRow}>
        {(['tous', 'non_vie', 'vie'] as const).map(f => (
          <TouchableOpacity key={f} onPress={() => setFiltreFamille(f)}
            style={[styles.filtreBtn, filtreFamille === f && styles.filtreBtnActive]}>
            <Text style={[styles.filtreBtnText, filtreFamille === f && styles.filtreBtnTextActive]}>
              {f === 'tous' ? 'Tous' : f === 'vie' ? '❤️ Vie' : '🛡️ Non-Vie'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Stats */}
      <View style={styles.statsRow}>
        {[
          { label: 'Total', val: sinistres.length, c: '#3b82f6' },
          { label: 'Vie', val: sinistres.filter(s => BRANCHES_CFG[s.branche]?.famille === 'vie').length, c: '#be185d' },
          { label: 'En cours', val: sinistres.filter(s => !['regle', 'rejete'].includes(s.statut)).length, c: '#f59e0b' },
          { label: 'Suspects', val: sinistres.filter(s => s.score_fraude > 60).length, c: '#ef4444' },
        ].map(s => (
          <View key={s.label} style={[styles.statCard, { borderTopColor: s.c }]}>
            <Text style={[styles.statVal, { color: s.c }]}>{s.val}</Text>
            <Text style={styles.statLabel}>{s.label}</Text>
          </View>
        ))}
      </View>

      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#1d4ed8" />}>
        {filtres.map(s => {
          const cfg = STATUT_CFG[s.statut] || { label: s.statut, bg: '#f1f5f9', text: '#374151' }
          const branchCfg = BRANCHES_CFG[s.branche]
          const isVie = branchCfg?.famille === 'vie'
          return (
            <TouchableOpacity key={s.id} style={[styles.card, isVie && { borderLeftWidth: 3, borderLeftColor: '#be185d' }]}
              onPress={() => setSelected(s)}>
              <View style={styles.cardHeader}>
                <Text style={styles.cardNumero}>{s.numero}</Text>
                <View style={[styles.badge, { backgroundColor: cfg.bg }]}>
                  <Text style={[styles.badgeText, { color: cfg.text }]}>{cfg.label}</Text>
                </View>
              </View>
              <Text style={styles.cardAssure}>{s.assure}</Text>
              <View style={styles.cardMeta}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Text style={[styles.branchBadge, { backgroundColor: (branchCfg?.couleur || '#64748b') + '20', color: branchCfg?.couleur || '#64748b' }]}>
                    {s.branche_cima} · {s.branche}
                  </Text>
                </View>
                <Text style={[styles.fraudeScore, { color: fraudeCouleur(s.score_fraude) }]}>Fraude {s.score_fraude}/100</Text>
              </View>
              <View style={styles.cardFooter}>
                <Text style={styles.cardMontant}>{s.montant_evalue.toLocaleString('fr-FR')} XAF</Text>
                <Text style={styles.compteCharge}>Cpt {s.compte_charge}</Text>
              </View>
            </TouchableOpacity>
          )
        })}
      </ScrollView>

      {/* Modal détail */}
      <Modal visible={!!selected} animationType="slide" presentationStyle="pageSheet">
        {selected && (
          <View style={styles.modal}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{selected.numero}</Text>
              <TouchableOpacity onPress={() => setSelected(null)}><Ionicons name="close" size={24} color="#374151" /></TouchableOpacity>
            </View>
            <ScrollView style={{ padding: 16 }}>
              {[
                { label: 'Assuré', value: selected.assure },
                { label: 'Branche CIMA', value: `${selected.branche_cima} — ${selected.branche}` },
                { label: 'Date sinistre', value: selected.date_sinistre },
                { label: 'Montant évalué', value: selected.montant_evalue.toLocaleString('fr-FR') + ' XAF' },
                { label: 'Statut', value: STATUT_CFG[selected.statut]?.label || selected.statut },
                { label: 'Score fraude IA', value: `${selected.score_fraude}/100` },
              ].map(f => (
                <View key={f.label} style={styles.detailRow}>
                  <Text style={styles.detailLabel}>{f.label}</Text>
                  <Text style={styles.detailValue}>{f.value}</Text>
                </View>
              ))}
              {/* Imputation comptable */}
              <View style={styles.imputationCard}>
                <Text style={styles.imputationTitle}>Imputation OHADA automatique</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
                  <Text style={styles.imputationLabel}>Charge sinistre :</Text>
                  <Text style={styles.imputationValue}>{selected.compte_charge} (PSCA)</Text>
                </View>
                <Text style={styles.imputationNote}>→ Imputation poussée vers ORASS/Mercure à la validation</Text>
              </View>
            </ScrollView>
          </View>
        )}
      </Modal>

      {/* Modal déclaration */}
      <Modal visible={declarerVisible} animationType="slide" presentationStyle="pageSheet">
        <View style={styles.modal}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>
              {etapeDecl === 'type' ? 'Type de sinistre' : etapeDecl === 'scan' ? `Scanner — ${typeChoisi?.label}` : etapeDecl === 'validation' ? 'Vérification IA' : 'Enregistré !'}
            </Text>
            <TouchableOpacity onPress={resetDecl}><Ionicons name="close" size={24} color="#374151" /></TouchableOpacity>
          </View>
          <ScrollView style={{ flex: 1, padding: 16 }}>

            {etapeDecl === 'type' && (
              <View>
                <Text style={styles.sectionLabel}>Assurance Non-Vie</Text>
                <View style={styles.typeGrid}>
                  {TYPES_SINISTRE_DECL.filter(t => t.famille === 'non_vie').map(t => (
                    <TouchableOpacity key={t.value} style={[styles.typeCard, typeChoisi?.value === t.value && { borderColor: t.couleur, backgroundColor: t.couleur + '15' }]}
                      onPress={() => setTypeChoisi(t)}>
                      <Ionicons name={t.icon as never} size={24} color={typeChoisi?.value === t.value ? t.couleur : '#94a3b8'} />
                      <Text style={[styles.typeCardLabel, typeChoisi?.value === t.value && { color: t.couleur }]}>{t.label}</Text>
                      <Text style={styles.typeCardCima}>{t.branche_cima}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={[styles.sectionLabel, { color: '#be185d', marginTop: 12 }]}>Assurance Vie</Text>
                <View style={styles.typeGrid}>
                  {TYPES_SINISTRE_DECL.filter(t => t.famille === 'vie').map(t => (
                    <TouchableOpacity key={t.value} style={[styles.typeCard, typeChoisi?.value === t.value && { borderColor: t.couleur, backgroundColor: t.couleur + '15' }]}
                      onPress={() => setTypeChoisi(t)}>
                      <Ionicons name={t.icon as never} size={24} color={typeChoisi?.value === t.value ? t.couleur : '#94a3b8'} />
                      <Text style={[styles.typeCardLabel, typeChoisi?.value === t.value && { color: t.couleur }]}>{t.label}</Text>
                      <Text style={styles.typeCardCima}>{t.branche_cima}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity style={[styles.nextBtn, !typeChoisi && { opacity: 0.4 }]}
                  onPress={() => typeChoisi && setEtapeDecl('scan')} disabled={!typeChoisi}>
                  <Ionicons name="camera" size={18} color="#fff" />
                  <Text style={styles.nextBtnText}>Scanner le document</Text>
                </TouchableOpacity>
              </View>
            )}

            {etapeDecl === 'scan' && (
              <View style={{ alignItems: 'center', paddingVertical: 16 }}>
                {imageUri ? <Image source={{ uri: imageUri }} style={{ width: '100%', height: 200, borderRadius: 12, marginBottom: 12 }} resizeMode="contain" /> :
                  <View style={[styles.scanZone, { borderColor: typeChoisi?.couleur || '#94a3b8' }]}>
                    <Ionicons name={(typeChoisi?.icon || 'document-outline') as never} size={48} color={typeChoisi?.couleur || '#94a3b8'} />
                    <Text style={styles.scanHint}>Scanner : {typeChoisi?.label}</Text>
                    <Text style={styles.scanSubHint}>{typeChoisi?.branche_cima} — Yukpo IA extrait automatiquement</Text>
                  </View>}
                {scanLoading ? <ActivityIndicator size="large" color="#1d4ed8" style={{ marginTop: 16 }} /> : (
                  <View style={{ width: '100%', gap: 10, marginTop: 8 }}>
                    <TouchableOpacity style={[styles.nextBtn, { backgroundColor: typeChoisi?.couleur || '#1d4ed8' }]} onPress={scannerDocument}>
                      <Ionicons name="camera" size={18} color="#fff" />
                      <Text style={styles.nextBtnText}>Prendre une photo</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.gallerieBtn} onPress={async () => {
                      const r = await ImagePicker.launchImageLibraryAsync({ quality: 0.85 })
                      if (!r.canceled) { setImageUri(r.assets[0].uri); setScanLoading(true); setTimeout(() => { setChampsExtraits(demoChamps(typeChoisi?.value || 'auto')); setScanLoading(false); setEtapeDecl('validation') }, 1500) }
                    }}>
                      <Ionicons name="images-outline" size={18} color="#374151" />
                      <Text style={styles.gallerieBtnText}>Depuis la galerie</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            )}

            {etapeDecl === 'validation' && (
              <View>
                <View style={styles.iaBanner}>
                  <Ionicons name="sparkles" size={14} color="#1d4ed8" />
                  <Text style={styles.iaBannerText}>Yukpo IA a extrait les informations — vérifiez avant de soumettre</Text>
                </View>
                {champsExtraits.map((c, i) => (
                  <View key={i} style={styles.champRow}>
                    <Text style={styles.champLabel}>{c.label}</Text>
                    <Text style={styles.champVal}>{c.valeur}</Text>
                  </View>
                ))}
                <TouchableOpacity style={[styles.nextBtn, { backgroundColor: '#10b981', marginTop: 16 }]} onPress={soumettreSinistre} disabled={submitLoading}>
                  {submitLoading ? <ActivityIndicator color="#fff" /> : <><Ionicons name="checkmark-circle" size={18} color="#fff" /><Text style={styles.nextBtnText}>Soumettre la déclaration</Text></>}
                </TouchableOpacity>
              </View>
            )}

            {etapeDecl === 'succes' && (
              <View style={{ alignItems: 'center', paddingVertical: 32 }}>
                <Ionicons name="checkmark-circle" size={64} color="#10b981" />
                <Text style={styles.succesTitle}>Sinistre déclaré !</Text>
                <Text style={styles.succesText}>Dossier enregistré — imputation comptable générée automatiquement.</Text>
                <TouchableOpacity style={[styles.nextBtn, { marginTop: 24 }]} onPress={resetDecl}>
                  <Text style={styles.nextBtnText}>Retour à la liste</Text>
                </TouchableOpacity>
              </View>
            )}
          </ScrollView>
        </View>
      </Modal>
    </View>
  )
}

// ─── Onglet Recours ───────────────────────────────────────────────────────────

function OngletRecoursMobile() {
  const [recours, setRecours] = useState<Recours[]>(RECOURS_DEMO)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ sinistre_ref: '', tiers: '', type: 'Subrogatoire', montant: '' })

  const RECOURS_STATUT_CFG: Record<string, { bg: string; text: string }> = {
    ouvert:   { bg: '#dbeafe', text: '#1e40af' },
    en_cours: { bg: '#fef3c7', text: '#92400e' },
    obtenu:   { bg: '#dcfce7', text: '#14532d' },
    ferme:    { bg: '#f1f5f9', text: '#374151' },
  }

  const soumettre = () => {
    const n: Recours = {
      id: Date.now().toString(),
      numero: `REC-2026-${String(recours.length + 1).padStart(3, '0')}`,
      sinistre_ref: form.sinistre_ref, tiers: form.tiers, type: form.type,
      montant_reclame: parseFloat(form.montant) || 0, statut: 'ouvert',
    }
    setRecours(p => [n, ...p])
    setShowForm(false)
    setForm({ sinistre_ref: '', tiers: '', type: 'Subrogatoire', montant: '' })
  }

  const fmt = (n: number) => n.toLocaleString('fr-FR') + ' XAF'

  return (
    <ScrollView style={{ flex: 1, backgroundColor: '#f1f5f9' }} contentContainerStyle={{ padding: 12 }}>
      <View style={styles.statsRow}>
        <View style={[styles.statCard, { borderTopColor: '#3b82f6' }]}>
          <Text style={[styles.statVal, { color: '#3b82f6' }]}>{recours.length}</Text>
          <Text style={styles.statLabel}>Dossiers</Text>
        </View>
        <View style={[styles.statCard, { borderTopColor: '#10b981' }]}>
          <Text style={[styles.statVal, { color: '#10b981', fontSize: 14 }]}>{fmt(recours.reduce((s, r) => s + (r.montant_obtenu || 0), 0))}</Text>
          <Text style={styles.statLabel}>Recouvré</Text>
        </View>
      </View>

      <TouchableOpacity style={[styles.nextBtn, { marginBottom: 12 }]} onPress={() => setShowForm(!showForm)}>
        <Ionicons name="add-circle-outline" size={18} color="#fff" />
        <Text style={styles.nextBtnText}>Nouveau recours</Text>
      </TouchableOpacity>

      {showForm && (
        <View style={styles.formCard}>
          {[
            { key: 'sinistre_ref', label: 'Référence sinistre', placeholder: 'SIN-2026-XXX' },
            { key: 'tiers', label: 'Tiers visé', placeholder: 'Compagnie / personne' },
            { key: 'montant', label: 'Montant réclamé (XAF)', placeholder: '2 500 000', numeric: true },
          ].map(f => (
            <View key={f.key} style={styles.inputGroup}>
              <Text style={styles.inputLabel}>{f.label}</Text>
              <TextInput style={styles.input} placeholder={f.placeholder} placeholderTextColor="#94a3b8"
                keyboardType={f.numeric ? 'numeric' : 'default'}
                value={(form as Record<string, string>)[f.key]}
                onChangeText={v => setForm(p => ({ ...p, [f.key]: v }))} />
            </View>
          ))}
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Type</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {['Subrogatoire', 'Contribution'].map(t => (
                <TouchableOpacity key={t} onPress={() => setForm(p => ({ ...p, type: t }))}
                  style={[styles.filtreBtn, form.type === t && styles.filtreBtnActive]}>
                  <Text style={[styles.filtreBtnText, form.type === t && styles.filtreBtnTextActive]}>{t}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          <TouchableOpacity style={[styles.nextBtn, { backgroundColor: '#10b981' }]} onPress={soumettre}>
            <Text style={styles.nextBtnText}>Enregistrer</Text>
          </TouchableOpacity>
        </View>
      )}

      {recours.map(r => {
        const cfg = RECOURS_STATUT_CFG[r.statut] || { bg: '#f1f5f9', text: '#374151' }
        return (
          <View key={r.id} style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardNumero}>{r.numero}</Text>
              <View style={[styles.badge, { backgroundColor: cfg.bg }]}>
                <Text style={[styles.badgeText, { color: cfg.text }]}>{r.statut.replace('_', ' ')}</Text>
              </View>
            </View>
            <Text style={styles.cardAssure}>{r.sinistre_ref} · {r.type}</Text>
            <Text style={[styles.cardAssure, { color: '#64748b', fontSize: 12 }]}>{r.tiers}</Text>
            <View style={styles.cardFooter}>
              <Text style={styles.cardMontant}>{fmt(r.montant_reclame)}</Text>
              {r.montant_obtenu ? <Text style={{ color: '#16a34a', fontSize: 12, fontWeight: '700' }}>✓ {fmt(r.montant_obtenu)}</Text> : null}
            </View>
          </View>
        )
      })}
    </ScrollView>
  )
}

// ─── Onglet Lettres ───────────────────────────────────────────────────────────

function OngletLettresMobile() {
  const [templateChoisi, setTemplateChoisi] = useState<string | null>(null)
  const [sinistreRef, setSinistreRef] = useState('')
  const [contexte, setContexte] = useState('')
  const [lettre, setLettre] = useState('')
  const [loading, setLoading] = useState(false)

  const generer = async () => {
    setLoading(true)
    const template = TEMPLATES_LETTRES.find(t => t.id === templateChoisi)
    try {
      const { data } = await apiClient.post('/api/v1/chat/message', {
        message: `Rédige une lettre professionnelle "${template?.label}" pour le sinistre ${sinistreRef}. Contexte : ${contexte}. Format CIMA, formules de politesse africaines.`,
        stream: false,
      })
      const d = data as Record<string, unknown>
      setLettre((d.response as string) || (d.content as string) || '')
    } catch {
      const today = new Date().toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })
      setLettre(demoLettre(templateChoisi || '', sinistreRef, today, contexte))
    } finally { setLoading(false) }
  }

  const demoLettre = (type: string, ref: string, date: string, ctx: string) => {
    const letters: Record<string, string> = {
      accuse: `Douala, le ${date}\n\nObjet : Accusé de réception — Dossier ${ref}\n\nMonsieur/Madame,\n\nNous accusons bonne réception de votre déclaration de sinistre sous la référence ${ref}.\n\nVotre dossier est en cours d'instruction. Délai CIMA : 30 jours.\n\nCordialement,\nLe Service Sinistres`,
      demande_pieces: `Douala, le ${date}\n\nObjet : Demande de pièces — Dossier ${ref}\n\nMonsieur/Madame,\n\nAfin de poursuivre l'instruction du dossier ${ref}, nous vous prions de transmettre :\n\n• Pièces justificatives originales\n• Relevé bancaire (RIB)\n• Tout document complémentaire\n\nDélai : 15 jours.\n\nCordialement,\nLe Gestionnaire`,
      rejet: `Douala, le ${date}\n\nObjet : Rejet de prise en charge — Dossier ${ref}\n\nMonsieur/Madame,\n\nSuivant examen du dossier ${ref}, votre demande ne peut être prise en charge.\n\nMotif : ${ctx || 'Exclusion contractuelle applicable'}\n\nRecours possible auprès de la CRCA (Art. 18 Code CIMA).\n\nCordialement,\nLe Directeur Technique`,
      notification_reglement: `Douala, le ${date}\n\nObjet : Notification de règlement — Dossier ${ref}\n\nMonsieur/Madame,\n\nNous avons le plaisir de vous informer que votre sinistre ${ref} a été réglé favorablement.\n\nVersement par virement sous 5 jours ouvrables.\n\nCordialement,\nLe Directeur Financier`,
    }
    return letters[type] || `Douala, le ${date}\n\nObjet : Correspondance sinistre ${ref}\n\n${ctx}\n\nCordialement,\nLe Service Sinistres`
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView style={{ flex: 1, backgroundColor: '#f1f5f9' }} contentContainerStyle={{ padding: 12 }}>

        <Text style={styles.sectionLabel}>Type de correspondance</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {TEMPLATES_LETTRES.map(t => (
            <TouchableOpacity key={t.id} onPress={() => setTemplateChoisi(t.id)}
              style={[styles.templateBtn, templateChoisi === t.id && styles.templateBtnActive]}>
              <Ionicons name={t.icon} size={16} color={templateChoisi === t.id ? '#1d4ed8' : '#94a3b8'} />
              <Text style={[styles.templateBtnText, templateChoisi === t.id && { color: '#1d4ed8' }]}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>Référence sinistre</Text>
          <TextInput style={styles.input} placeholder="SIN-2026-XXX" placeholderTextColor="#94a3b8"
            value={sinistreRef} onChangeText={setSinistreRef} />
        </View>
        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>Contexte / Motif</Text>
          <TextInput style={[styles.input, { height: 70 }]} placeholder="Motif, montant, détails…" placeholderTextColor="#94a3b8"
            value={contexte} onChangeText={setContexte} multiline />
        </View>

        <TouchableOpacity style={[styles.nextBtn, (!templateChoisi || loading) && { opacity: 0.5 }]}
          onPress={generer} disabled={!templateChoisi || loading}>
          {loading ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="sparkles" size={18} color="#fff" />}
          <Text style={styles.nextBtnText}>{loading ? 'Génération…' : 'Générer avec Yukpo IA'}</Text>
        </TouchableOpacity>

        {lettre ? (
          <View style={styles.formCard}>
            <Text style={styles.sectionLabel}>Lettre générée — modifiez si nécessaire</Text>
            <TextInput style={[styles.input, { height: 280, fontFamily: 'monospace', fontSize: 12, marginBottom: 12 }]}
              value={lettre} onChangeText={setLettre} multiline />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity style={[styles.nextBtn, { flex: 1, backgroundColor: '#10b981' }]}
                onPress={() => Alert.alert('Email', 'Envoi email simulé')}>
                <Ionicons name="mail-outline" size={16} color="#fff" />
                <Text style={styles.nextBtnText}>Envoyer</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.gallerieBtn, { flex: 1 }]}
                onPress={() => Alert.alert('PDF', 'Export PDF simulé')}>
                <Ionicons name="document-outline" size={16} color="#374151" />
                <Text style={styles.gallerieBtnText}>Télécharger</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

// ─── Onglet Fournisseurs (mobile) ─────────────────────────────────────────────

interface PieceMobile {
  id: string; fournisseur: string; type_fourn: string
  sinistre_ref: string; type_doc: string; fichier: string
  date: string; statut: 'en_attente' | 'valide' | 'rejete'; score: number | null
}

const PIECES_MOBILE: PieceMobile[] = [
  { id: 'f1', fournisseur: 'Garage Central YDE', type_fourn: 'Garage', sinistre_ref: 'SIN-2026-0342', type_doc: 'Facture réparation', fichier: 'facture_342.pdf', date: '2026-04-08', statut: 'en_attente', score: null },
  { id: 'f2', fournisseur: 'Clinique Les Sœurs', type_fourn: 'Clinique', sinistre_ref: 'SIN-2026-0289', type_doc: 'Rapport médical', fichier: 'rapport_289.pdf', date: '2026-04-07', statut: 'valide', score: 78 },
  { id: 'f3', fournisseur: 'Expert SARL', type_fourn: 'Expert', sinistre_ref: 'SIN-2026-0301', type_doc: "Rapport expertise", fichier: 'expertise_301.pdf', date: '2026-04-06', statut: 'valide', score: 92 },
  { id: 'f4', fournisseur: 'Pharmacie Centre', type_fourn: 'Pharmacie', sinistre_ref: 'SIN-2026-0255', type_doc: 'Facture pharmacie', fichier: 'pharma_255.pdf', date: '2026-04-05', statut: 'rejete', score: 34 },
]

function OngletFournisseursMobile() {
  const [pieces, setPieces] = useState<PieceMobile[]>(PIECES_MOBILE)
  const [analysing, setAnalysing] = useState<string | null>(null)

  const analyser = async (id: string) => {
    setAnalysing(id)
    await new Promise(r => setTimeout(r, 1500))
    const score = Math.floor(Math.random() * 75) + 20
    setPieces(prev => prev.map(p => p.id === id ? { ...p, score } : p))
    setAnalysing(null)
  }
  const valider = (id: string) => setPieces(prev => prev.map(p => p.id === id ? { ...p, statut: 'valide' as const } : p))
  const rejeter = (id: string) => {
    Alert.alert('Rejeter', 'Confirmer le rejet ?', [
      { text: 'Annuler', style: 'cancel' },
      { text: 'Rejeter', style: 'destructive', onPress: () => setPieces(prev => prev.map(p => p.id === id ? { ...p, statut: 'rejete' as const } : p)) },
    ])
  }

  const enAttente = pieces.filter(p => p.statut === 'en_attente').length

  return (
    <ScrollView contentContainerStyle={{ padding: 12, gap: 10, paddingBottom: 30 }}>
      {/* Stats */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {[
          { label: 'En attente', v: enAttente, c: '#f59e0b' },
          { label: 'Validés', v: pieces.filter(p => p.statut === 'valide').length, c: '#10b981' },
          { label: 'Rejetés', v: pieces.filter(p => p.statut === 'rejete').length, c: '#ef4444' },
        ].map((k, i) => (
          <View key={i} style={{ flex: 1, backgroundColor: '#fff', borderRadius: 10, padding: 10, alignItems: 'center', borderTopWidth: 3, borderTopColor: k.c }}>
            <Text style={{ fontSize: 20, fontWeight: '800', color: k.c }}>{k.v}</Text>
            <Text style={{ fontSize: 9, color: '#94a3b8', fontWeight: '600', marginTop: 2 }}>{k.label}</Text>
          </View>
        ))}
      </View>

      {pieces.map(p => {
        const sCls = p.statut === 'en_attente' ? { bg: '#fffbeb', c: '#d97706' } : p.statut === 'valide' ? { bg: '#f0fdf4', c: '#16a34a' } : { bg: '#fef2f2', c: '#dc2626' }
        return (
          <View key={p.id} style={{ backgroundColor: '#fff', borderRadius: 12, padding: 12, elevation: 1 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, fontWeight: '700', color: '#1e293b' }}>{p.fournisseur}</Text>
                <Text style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{p.type_doc}</Text>
                <Text style={{ fontSize: 11, fontFamily: 'monospace', color: '#1d4ed8', marginTop: 2 }}>{p.sinistre_ref}</Text>
              </View>
              <View style={{ alignItems: 'flex-end', gap: 4 }}>
                <View style={{ backgroundColor: sCls.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: sCls.c }}>
                    {p.statut === 'en_attente' ? 'En attente' : p.statut === 'valide' ? 'Validé' : 'Rejeté'}
                  </Text>
                </View>
                {p.score !== null && (
                  <View style={{ backgroundColor: p.score >= 70 ? '#f0fdf4' : p.score >= 45 ? '#fffbeb' : '#fef2f2', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 20 }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: p.score >= 70 ? '#16a34a' : p.score >= 45 ? '#d97706' : '#dc2626' }}>
                      IA {p.score}/100
                    </Text>
                  </View>
                )}
              </View>
            </View>
            <Text style={{ fontSize: 10, color: '#94a3b8' }}>{p.fichier} · {p.date}</Text>
            {p.statut === 'en_attente' && (
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                {p.score === null && (
                  <TouchableOpacity
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#7c3aed', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}
                    onPress={() => analyser(p.id)} disabled={analysing === p.id}>
                    {analysing === p.id ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="sparkles-outline" size={12} color="#fff" />}
                    <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{analysing === p.id ? 'Analyse…' : 'Analyser IA'}</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#10b981', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}
                  onPress={() => valider(p.id)}>
                  <Ionicons name="checkmark-outline" size={12} color="#fff" />
                  <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>Valider → ORASS</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#fef2f2', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}
                  onPress={() => rejeter(p.id)}>
                  <Ionicons name="close-outline" size={12} color="#ef4444" />
                  <Text style={{ color: '#ef4444', fontSize: 11, fontWeight: '700' }}>Rejeter</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )
      })}
    </ScrollView>
  )
}

// ─── Composant principal ──────────────────────────────────────────────────────

export default function SinistresScreen() {
  const [onglet, setOnglet] = useState<OngletType>('dossiers')

  return (
    <View style={{ flex: 1, backgroundColor: '#f1f5f9' }}>
      {/* Onglets */}
      <View style={styles.ongletBar}>
        {([
          { id: 'dossiers', label: 'Dossiers', icon: 'shield-outline' },
          { id: 'recours', label: 'Recours', icon: 'refresh-outline' },
          { id: 'lettres', label: 'Lettres IA', icon: 'pencil-outline' },
          { id: 'fournisseurs', label: 'Fourn.', icon: 'storefront-outline' },
          { id: 'courtiers', label: 'Courtiers', icon: 'briefcase-outline' },
        ] as const).map(o => (
          <TouchableOpacity key={o.id} onPress={() => setOnglet(o.id as OngletType)}
            style={[styles.ongletBtn, onglet === o.id && styles.ongletBtnActive]}>
            <Ionicons name={o.icon as never} size={14} color={onglet === o.id ? '#1d4ed8' : '#94a3b8'} />
            <Text style={[styles.ongletBtnText, onglet === o.id && styles.ongletBtnTextActive]}>{o.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {onglet === 'dossiers' && <OngletDossiers />}
      {onglet === 'recours' && <OngletRecoursMobile />}
      {onglet === 'lettres' && <OngletLettresMobile />}
      {onglet === 'fournisseurs' && <OngletFournisseursMobile />}
      {onglet === 'courtiers' && <OngletCourtiersSinistres />}
    </View>
  )
}

function OngletCourtiersSinistres() {
  const DOCS = [
    { id: 'c1', courtier: 'Cabinet Assur-Plus', ref: 'SIN-2026-0234', type: 'Déclaration sinistre', statut: 'valide', score: 87 },
    { id: 'c2', courtier: 'Transcam SARL', ref: 'SIN-2026-0301', type: 'Constat amiable', statut: 'en_attente', score: null },
    { id: 'c3', courtier: 'Ngando Ind.', ref: 'SIN-2026-0412', type: 'Rapport expertise', statut: 'rejete', score: 22 },
  ]
  const statCls = (s: string) => s === 'valide' ? '#16a34a' : s === 'rejete' ? '#dc2626' : '#f59e0b'
  const statLabel = (s: string) => s === 'valide' ? 'Validé' : s === 'rejete' ? 'Rejeté' : 'En attente'

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 12, gap: 10 }}>
      <View style={{ backgroundColor: '#eff6ff', borderRadius: 10, padding: 12, marginBottom: 4 }}>
        <Text style={{ fontSize: 12, color: '#1e40af', fontWeight: '600' }}>Documents sinistres reçus des courtiers</Text>
        <Text style={{ fontSize: 11, color: '#3b82f6', marginTop: 3 }}>Analysez chaque pièce par OCR avant injection dans le SI.</Text>
      </View>
      {DOCS.map(d => (
        <View key={d.id} style={{ backgroundColor: '#fff', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#e2e8f0' }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>{d.courtier}</Text>
              <Text style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{d.type} · {d.ref}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: statCls(d.statut) + '20', paddingHorizontal: 7, paddingVertical: 3, borderRadius: 8 }}>
              <Ionicons name={d.statut === 'valide' ? 'checkmark-circle-outline' : d.statut === 'rejete' ? 'close-circle-outline' : 'time-outline'} size={12} color={statCls(d.statut)} />
              <Text style={{ fontSize: 10, fontWeight: '700', color: statCls(d.statut) }}>{statLabel(d.statut)}</Text>
            </View>
          </View>
          {d.score != null && (
            <Text style={{ fontSize: 11, color: d.score > 70 ? '#166534' : '#dc2626', marginTop: 6, fontWeight: '600' }}>Score IA : {d.score}%</Text>
          )}
          {d.statut === 'en_attente' && (
            <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: '#1d4ed8', paddingVertical: 8, borderRadius: 8, marginTop: 10 }}>
              <Ionicons name="sparkles-outline" size={14} color="#fff" />
              <Text style={{ fontSize: 12, color: '#fff', fontWeight: '600' }}>Analyser OCR</Text>
            </TouchableOpacity>
          )}
        </View>
      ))}
    </ScrollView>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  ongletBar: { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  ongletBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  ongletBtnActive: { borderBottomColor: '#1d4ed8' },
  ongletBtnText: { fontSize: 12, color: '#94a3b8', fontWeight: '600' },
  ongletBtnTextActive: { color: '#1d4ed8' },
  topBar: { flexDirection: 'row', alignItems: 'center', margin: 10, gap: 8 },
  searchBar: { flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: '#e2e8f0' },
  searchInput: { flex: 1, fontSize: 13, color: '#1e293b' },
  declarerBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#1d4ed8', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  declarerBtnText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  filtreRow: { flexDirection: 'row', gap: 6, paddingHorizontal: 10, marginBottom: 8 },
  filtreBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: '#fff', borderWidth: 1, borderColor: '#e2e8f0' },
  filtreBtnActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  filtreBtnText: { fontSize: 11, color: '#64748b', fontWeight: '600' },
  filtreBtnTextActive: { color: '#fff' },
  statsRow: { flexDirection: 'row', gap: 6, marginHorizontal: 10, marginBottom: 8 },
  statCard: { flex: 1, backgroundColor: '#fff', borderRadius: 8, padding: 8, alignItems: 'center', borderTopWidth: 3, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, elevation: 1 },
  statVal: { fontSize: 17, fontWeight: 'bold' },
  statLabel: { fontSize: 9, color: '#64748b', marginTop: 2 },
  card: { backgroundColor: '#fff', borderRadius: 12, margin: 10, marginTop: 0, padding: 13, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, elevation: 2 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  cardNumero: { fontSize: 12, fontWeight: 'bold', color: '#1e293b', fontFamily: 'monospace' },
  badge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 20 },
  badgeText: { fontSize: 10, fontWeight: '600' },
  cardAssure: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 4 },
  cardMeta: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  branchBadge: { fontSize: 10, fontWeight: '700', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12 },
  fraudeScore: { fontSize: 11, fontWeight: 'bold' },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderTopWidth: 1, borderTopColor: '#f1f5f9', paddingTop: 6 },
  cardMontant: { fontSize: 12, fontWeight: 'bold', color: '#1e293b' },
  compteCharge: { fontSize: 10, color: '#1d4ed8', fontFamily: 'monospace', backgroundColor: '#eff6ff', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  modal: { flex: 1, backgroundColor: '#fff' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e2e8f0', paddingTop: 48 },
  modalTitle: { fontSize: 16, fontWeight: 'bold', color: '#1e293b' },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  detailLabel: { fontSize: 12, color: '#64748b' },
  detailValue: { fontSize: 12, fontWeight: '600', color: '#1e293b', flex: 1, textAlign: 'right' },
  imputationCard: { backgroundColor: '#eff6ff', borderRadius: 10, padding: 12, marginTop: 12 },
  imputationTitle: { fontSize: 11, fontWeight: '700', color: '#1d4ed8', textTransform: 'uppercase', letterSpacing: 0.5 },
  imputationLabel: { fontSize: 11, color: '#1e40af' },
  imputationValue: { fontSize: 11, fontWeight: '700', color: '#1e40af', fontFamily: 'monospace' },
  imputationNote: { fontSize: 10, color: '#3b82f6', marginTop: 4 },
  sectionLabel: { fontSize: 11, fontWeight: '700', color: '#374151', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  typeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  typeCard: { width: '47%', borderWidth: 2, borderColor: '#e2e8f0', borderRadius: 12, padding: 10, alignItems: 'center', gap: 4 },
  typeCardLabel: { fontSize: 11, color: '#64748b', textAlign: 'center', fontWeight: '600' },
  typeCardCima: { fontSize: 9, color: '#94a3b8', fontFamily: 'monospace' },
  scanZone: { borderWidth: 2, borderStyle: 'dashed', borderRadius: 16, padding: 28, alignItems: 'center', marginBottom: 20, width: '100%' },
  scanHint: { fontSize: 13, fontWeight: '600', color: '#374151', marginTop: 10, textAlign: 'center' },
  scanSubHint: { fontSize: 10, color: '#94a3b8', marginTop: 3, textAlign: 'center' },
  nextBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1d4ed8', borderRadius: 10, paddingVertical: 13, marginTop: 8 },
  nextBtnText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  gallerieBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#f1f5f9', borderRadius: 10, paddingVertical: 13, borderWidth: 1, borderColor: '#e2e8f0' },
  gallerieBtnText: { color: '#374151', fontWeight: '600', fontSize: 13 },
  iaBanner: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#eff6ff', borderRadius: 10, padding: 10, marginBottom: 10 },
  iaBannerText: { fontSize: 11, color: '#1d4ed8', flex: 1 },
  champRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  champLabel: { fontSize: 12, color: '#64748b', textTransform: 'capitalize' },
  champVal: { fontSize: 12, fontWeight: '600', color: '#1e293b', flex: 1, textAlign: 'right' },
  succesTitle: { fontSize: 18, fontWeight: 'bold', color: '#1e293b', marginTop: 12, marginBottom: 6 },
  succesText: { fontSize: 12, color: '#64748b', textAlign: 'center' },
  inputGroup: { marginBottom: 10 },
  inputLabel: { fontSize: 12, fontWeight: '600', color: '#374151', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: '#1e293b', backgroundColor: '#f9fafb' },
  formCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 12, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, elevation: 2 },
  templateBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1.5, borderColor: '#e2e8f0', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: '#fff' },
  templateBtnActive: { borderColor: '#1d4ed8', backgroundColor: '#eff6ff' },
  templateBtnText: { fontSize: 11, color: '#64748b', fontWeight: '600' },
})
