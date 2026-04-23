import { useState, useEffect, useRef } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, Dimensions, TextInput, Alert, ActivityIndicator,
  Platform,
} from 'react-native'
import { LineChart, BarChart } from 'react-native-chart-kit'
import { Ionicons } from '@expo/vector-icons'
import * as ImagePicker from 'expo-image-picker'
import { courtiersAPI } from '../../src/api/client'
import { DemoBanner } from '../../src/components/DemoBanner'

const SCREEN_WIDTH = Dimensions.get('window').width

// ─── Données démo ─────────────────────────────────────────────────────────────

const COMMISSIONS_DEMO = [
  { mois: 'Oct', montant: 1850 },
  { mois: 'Nov', montant: 2120 },
  { mois: 'Déc', montant: 2580 },
  { mois: 'Jan', montant: 1960 },
  { mois: 'Fév', montant: 2340 },
  { mois: 'Mar', montant: 2710 },
]

const PRODUCTIONS_DEMO = [
  { branche: 'Auto', primes: 8.5, objectif: 10.0 },
  { branche: 'Vie', primes: 4.2, objectif: 5.0 },
  { branche: 'MRH', primes: 2.8, objectif: 3.0 },
  { branche: 'Santé', primes: 1.9, objectif: 2.5 },
]

const DOCS_DEMO: DocCourtier[] = [
  {
    id: '1', courtier: 'Cabinet Assur-Plus', categorie: 'souscription',
    reference: 'POL-2026-0412', type_document: 'Proposition d\'assurance',
    fichier_nom: 'proposition_auto.pdf', date_envoi: '2026-04-09',
    statut: 'en_analyse', score_ia: 92,
  },
  {
    id: '2', courtier: 'Transcam SARL', categorie: 'sinistre',
    reference: 'SIN-2026-0234', type_document: 'Déclaration sinistre',
    fichier_nom: 'declaration_fouda.pdf', date_envoi: '2026-04-08',
    statut: 'valide', score_ia: 87,
  },
  {
    id: '3', courtier: 'Agence YK Courtage', categorie: 'comptabilite',
    reference: 'FACT-2026-0089', type_document: 'Bordereaux de primes',
    fichier_nom: 'bordereau_mars.pdf', date_envoi: '2026-04-09',
    statut: 'rejete', score_ia: 28,
  },
  {
    id: '4', courtier: 'Ngando Ind.', categorie: 'souscription',
    reference: 'POL-2026-0415', type_document: 'Carte grise',
    fichier_nom: 'cg_ngando.jpg', date_envoi: '2026-04-10',
    statut: 'en_attente',
  },
]

const CHART_CONFIG = {
  backgroundGradientFrom: '#fff',
  backgroundGradientTo: '#fff',
  color: (opacity = 1) => `rgba(29, 78, 216, ${opacity})`,
  strokeWidth: 2.5,
  propsForLabels: { fontSize: 10 },
}

// ─── Types ─────────────────────────────────────────────────────────────────────

type OngletType = 'dashboard' | 'portail' | 'documents' | 'commissions'
type CategorieDoc = 'souscription' | 'sinistre' | 'comptabilite'
type StatutDoc = 'en_attente' | 'en_analyse' | 'valide' | 'rejete'

interface DocCourtier {
  id: string
  courtier: string
  categorie: CategorieDoc
  reference: string
  type_document: string
  fichier_nom: string
  date_envoi: string
  statut: StatutDoc
  score_ia?: number
}

const TYPES_DOC: Record<CategorieDoc, string[]> = {
  souscription: ['Proposition d\'assurance', 'Carte grise', 'CNI assuré', 'KYC client'],
  sinistre: ['Déclaration sinistre', 'Constat amiable', 'Rapport expertise', 'Facture réparation'],
  comptabilite: ['Bordereaux de primes', 'Relevé commissions', 'Facture honoraires', 'Quittance paiement'],
}

const STATUT_CFG: Record<StatutDoc, { label: string; color: string; icon: string }> = {
  en_attente: { label: 'En attente', color: '#64748b', icon: 'time-outline' },
  en_analyse: { label: 'Analyse YukpoPro', color: '#1d4ed8', icon: 'sparkles-outline' },
  valide: { label: 'Validé', color: '#16a34a', icon: 'checkmark-circle-outline' },
  rejete: { label: 'Rejeté', color: '#dc2626', icon: 'close-circle-outline' },
}

const CAT_CFG: Record<CategorieDoc, { label: string; icon: string; color: string }> = {
  souscription: { label: 'Souscription', icon: 'document-text-outline', color: '#3b82f6' },
  sinistre: { label: 'Sinistre', icon: 'warning-outline', color: '#f59e0b' },
  comptabilite: { label: 'Comptabilité', icon: 'cash-outline', color: '#10b981' },
}

// ─── Portail Courtier ─────────────────────────────────────────────────────────

function PortailCourtier({ onEnvoi }: { onEnvoi: (d: DocCourtier) => void }) {
  const [nomCourtier, setNomCourtier] = useState('')
  const [categorie, setCategorie] = useState<CategorieDoc>('souscription')
  const [reference, setReference] = useState('')
  const [typeDoc, setTypeDoc] = useState(TYPES_DOC['souscription'][0])
  const [fichierNom, setFichierNom] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [succes, setSucces] = useState(false)

  const choisirCategorie = (cat: CategorieDoc) => {
    setCategorie(cat)
    setTypeDoc(TYPES_DOC[cat][0])
  }

  const scannerDocument = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync()
    if (status !== 'granted') {
      Alert.alert('Permission requise', 'Accès à la caméra nécessaire pour scanner.')
      return
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8 })
    if (!result.canceled && result.assets[0]) {
      setFichierNom(`doc_${Date.now()}.jpg`)
    }
  }

  const choisirFichier = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 })
    if (!result.canceled && result.assets[0]) {
      setFichierNom(result.assets[0].fileName || `fichier_${Date.now()}.jpg`)
    }
  }

  const soumettre = async () => {
    if (!nomCourtier || !reference || !fichierNom) {
      Alert.alert('Champs manquants', 'Veuillez remplir tous les champs et joindre un fichier.')
      return
    }
    setLoading(true)
    await new Promise(r => setTimeout(r, 1200))
    const doc: DocCourtier = {
      id: Date.now().toString(),
      courtier: nomCourtier,
      categorie,
      reference,
      type_document: typeDoc,
      fichier_nom: fichierNom,
      date_envoi: new Date().toISOString().slice(0, 10),
      statut: 'en_attente',
    }
    onEnvoi(doc)
    setLoading(false)
    setSucces(true)
  }

  if (succes) {
    return (
      <View style={styles.succesContainer}>
        <View style={styles.succesIcon}>
          <Ionicons name="checkmark-circle" size={48} color="#16a34a" />
        </View>
        <Text style={styles.succesTitle}>Document transmis !</Text>
        <Text style={styles.succesText}>La compagnie a reçu votre document. YukpoPro va l'analyser automatiquement.</Text>
        <TouchableOpacity style={styles.succesBtn} onPress={() => { setSucces(false); setFichierNom(null); setNomCourtier(''); setReference('') }}>
          <Text style={styles.succesBtnText}>Envoyer un autre document</Text>
        </TouchableOpacity>
      </View>
    )
  }

  return (
    <View style={styles.portailContainer}>
      <View style={styles.infoBox}>
        <Ionicons name="shield-checkmark-outline" size={16} color="#1d4ed8" />
        <Text style={styles.infoText}>Transmettez vos documents scannés directement à la compagnie. YukpoPro analyse chaque pièce avant validation.</Text>
      </View>

      <Text style={styles.fieldLabel}>Votre cabinet / raison sociale *</Text>
      <TextInput
        style={styles.input}
        placeholder="Cabinet Assur-Plus Douala…"
        value={nomCourtier}
        onChangeText={setNomCourtier}
      />

      <Text style={styles.fieldLabel}>Catégorie du document *</Text>
      <View style={styles.catRow}>
        {(['souscription', 'sinistre', 'comptabilite'] as CategorieDoc[]).map(cat => (
          <TouchableOpacity
            key={cat}
            style={[styles.catBtn, categorie === cat && styles.catBtnActive]}
            onPress={() => choisirCategorie(cat)}
          >
            <Ionicons name={CAT_CFG[cat].icon as never} size={14} color={categorie === cat ? '#fff' : '#64748b'} />
            <Text style={[styles.catBtnText, categorie === cat && styles.catBtnTextActive]}>
              {CAT_CFG[cat].label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.fieldLabel}>Référence dossier *</Text>
      <TextInput
        style={[styles.input, { fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace' }]}
        placeholder={categorie === 'sinistre' ? 'SIN-2026-XXX' : 'POL-2026-XXX'}
        value={reference}
        onChangeText={setReference}
        autoCapitalize="characters"
      />

      <Text style={styles.fieldLabel}>Type de document</Text>
      <View style={styles.typeDocList}>
        {TYPES_DOC[categorie].map(t => (
          <TouchableOpacity
            key={t}
            style={[styles.typeDocBtn, typeDoc === t && styles.typeDocBtnActive]}
            onPress={() => setTypeDoc(t)}
          >
            <Text style={[styles.typeDocText, typeDoc === t && styles.typeDocTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.fieldLabel}>Document scanné *</Text>
      <View style={styles.uploadRow}>
        <TouchableOpacity style={[styles.uploadBtn, { flex: 1 }]} onPress={scannerDocument}>
          <Ionicons name="camera-outline" size={20} color="#1d4ed8" />
          <Text style={styles.uploadBtnText}>Scanner</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.uploadBtn, { flex: 1 }]} onPress={choisirFichier}>
          <Ionicons name="folder-outline" size={20} color="#1d4ed8" />
          <Text style={styles.uploadBtnText}>Galerie / Fichier</Text>
        </TouchableOpacity>
      </View>

      {fichierNom && (
        <View style={styles.fichierPreview}>
          <Ionicons name="document-outline" size={16} color="#1d4ed8" />
          <Text style={styles.fichierNom}>{fichierNom}</Text>
          <TouchableOpacity onPress={() => setFichierNom(null)}>
            <Ionicons name="close-circle" size={18} color="#94a3b8" />
          </TouchableOpacity>
        </View>
      )}

      <TouchableOpacity
        style={[styles.submitBtn, (!nomCourtier || !reference || !fichierNom) && styles.submitBtnDisabled]}
        onPress={soumettre}
        disabled={!nomCourtier || !reference || !fichierNom || loading}
      >
        {loading
          ? <ActivityIndicator color="#fff" size="small" />
          : <>
            <Ionicons name="cloud-upload-outline" size={18} color="#fff" />
            <Text style={styles.submitBtnText}>Transmettre à la compagnie</Text>
          </>
        }
      </TouchableOpacity>
    </View>
  )
}

// ─── Documents reçus ──────────────────────────────────────────────────────────

function DocumentsRecus({ documents, onUpdate }: { documents: DocCourtier[]; onUpdate: (d: DocCourtier) => void }) {
  const [analysing, setAnalysing] = useState<string | null>(null)

  const lancerAnalyse = async (d: DocCourtier) => {
    setAnalysing(d.id)
    onUpdate({ ...d, statut: 'en_analyse' })
    await new Promise(r => setTimeout(r, 2000))
    const score = Math.floor(Math.random() * 40) + 55
    onUpdate({ ...d, statut: 'en_analyse', score_ia: score })
    setAnalysing(null)
  }

  const valider = (d: DocCourtier) => onUpdate({ ...d, statut: 'valide' })
  const rejeter = (d: DocCourtier) => onUpdate({ ...d, statut: 'rejete' })

  const enAttente = documents.filter(d => d.statut === 'en_attente').length

  return (
    <View>
      {enAttente > 0 && (
        <View style={styles.alerteBanner}>
          <Ionicons name="time-outline" size={14} color="#92400e" />
          <Text style={styles.alerteBannerText}>{enAttente} document(s) en attente d'analyse</Text>
        </View>
      )}

      {documents.map(d => {
        const scfg = STATUT_CFG[d.statut]
        const ccfg = CAT_CFG[d.categorie]
        return (
          <View key={d.id} style={[styles.docCard, d.statut === 'rejete' ? styles.docCardRejete : d.statut === 'valide' ? styles.docCardValide : {}]}>
            <View style={styles.docHeader}>
              <View style={[styles.docCatIcon, { backgroundColor: ccfg.color + '20' }]}>
                <Ionicons name={ccfg.icon as never} size={18} color={ccfg.color} />
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Text style={styles.docCourtier}>{d.courtier}</Text>
                <Text style={styles.docMeta}>{d.type_document} · {d.reference}</Text>
                <Text style={styles.docFichier}>{d.fichier_nom}</Text>
              </View>
              <View style={styles.docStatutBadge}>
                <Ionicons name={scfg.icon as never} size={12} color={scfg.color} />
                <Text style={[styles.docStatutText, { color: scfg.color }]}>{scfg.label}</Text>
              </View>
            </View>

            {d.score_ia != null && (
              <View style={[styles.scoreRow, { backgroundColor: d.score_ia > 80 ? '#dcfce7' : d.score_ia > 60 ? '#fef9c3' : '#fee2e2' }]}>
                <Text style={[styles.scoreText, { color: d.score_ia > 80 ? '#166534' : d.score_ia > 60 ? '#854d0e' : '#991b1b' }]}>
                  Score : {d.score_ia}%
                </Text>
              </View>
            )}

            <View style={styles.docActions}>
              {d.statut === 'en_attente' && (
                <TouchableOpacity
                  style={styles.actionBtnPrimary}
                  onPress={() => lancerAnalyse(d)}
                  disabled={analysing === d.id}
                >
                  {analysing === d.id
                    ? <ActivityIndicator size="small" color="#fff" />
                    : <><Ionicons name="sparkles-outline" size={14} color="#fff" /><Text style={styles.actionBtnText}>Analyser</Text></>
                  }
                </TouchableOpacity>
              )}
              {d.statut === 'en_analyse' && d.score_ia != null && (
                <>
                  <TouchableOpacity style={styles.actionBtnGreen} onPress={() => valider(d)}>
                    <Ionicons name="checkmark-outline" size={14} color="#fff" />
                    <Text style={styles.actionBtnText}>Valider → SI</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.actionBtnRed} onPress={() => rejeter(d)}>
                    <Ionicons name="close-outline" size={14} color="#dc2626" />
                    <Text style={[styles.actionBtnText, { color: '#dc2626' }]}>Rejeter</Text>
                  </TouchableOpacity>
                </>
              )}
              {d.statut === 'valide' && (
                <View style={styles.valideLabel}>
                  <Ionicons name="checkmark-circle" size={14} color="#16a34a" />
                  <Text style={styles.valideLabelText}>Injecté dans le SI</Text>
                </View>
              )}
            </View>
          </View>
        )
      })}

      {documents.length === 0 && (
        <View style={styles.emptyState}>
          <Ionicons name="inbox-outline" size={40} color="#cbd5e1" />
          <Text style={styles.emptyStateText}>Aucun document reçu</Text>
        </View>
      )}
    </View>
  )
}

// ─── Écran principal ──────────────────────────────────────────────────────────

export default function CourtiersScreen() {
  const [refreshing, setRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [onglet, setOnglet] = useState<OngletType>('dashboard')
  const [documents, setDocuments] = useState<DocCourtier[]>(DOCS_DEMO)

  const charger = async () => {
    try { await courtiersAPI.getTableauBord() } catch { /* demo */ } finally {
      setLoading(false); setRefreshing(false)
    }
  }

  useEffect(() => { charger() }, [])
  const onRefresh = () => { setRefreshing(true); charger() }

  const kpis = [
    { label: 'Production MTD', value: '17.4M XAF', variation: '+12%', couleur: '#3b82f6', icon: 'trending-up-outline' },
    { label: 'Commissions Q1', value: '7.2M XAF', variation: '+8%', couleur: '#10b981', icon: 'cash-outline' },
    { label: 'Polices actives', value: '1 284', variation: '+47', couleur: '#f59e0b', icon: 'document-text-outline' },
    { label: 'Taux réalisation', value: '87%', variation: '-3 pts', couleur: '#8b5cf6', icon: 'analytics-outline' },
  ]

  const enAttenteCount = documents.filter(d => d.statut === 'en_attente').length

  const onglets: { key: OngletType; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'Vue générale', icon: 'stats-chart-outline' },
    { key: 'portail', label: 'Portail', icon: 'cloud-upload-outline' },
    { key: 'documents', label: 'Documents', icon: 'inbox-outline' },
    { key: 'commissions', label: 'Commissions', icon: 'cash-outline' },
  ]

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#1d4ed8" />}
    >
      <DemoBanner style={{ marginHorizontal: 12, marginTop: 8 }} />

      {/* KPI Cards */}
      <View style={styles.kpiGrid}>
        {kpis.map((k, i) => (
          <View key={i} style={styles.kpiCard}>
            <View style={[styles.kpiIcon, { backgroundColor: k.couleur + '20' }]}>
              <Ionicons name={k.icon as never} size={18} color={k.couleur} />
            </View>
            <Text style={styles.kpiValue}>{k.value}</Text>
            <Text style={styles.kpiLabel}>{k.label}</Text>
            <Text style={[styles.kpiVariation, { color: k.variation.startsWith('+') ? '#16a34a' : '#dc2626' }]}>
              {k.variation}
            </Text>
          </View>
        ))}
      </View>

      {/* Onglets */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsScroll}>
        <View style={styles.tabs}>
          {onglets.map(t => (
            <TouchableOpacity
              key={t.key}
              style={[styles.tab, onglet === t.key && styles.tabActive]}
              onPress={() => setOnglet(t.key)}
            >
              <Ionicons name={t.icon as never} size={14} color={onglet === t.key ? '#1d4ed8' : '#64748b'} />
              <Text style={[styles.tabText, onglet === t.key && styles.tabTextActive]}>{t.label}</Text>
              {t.key === 'documents' && enAttenteCount > 0 && (
                <View style={styles.tabBadge}>
                  <Text style={styles.tabBadgeText}>{enAttenteCount}</Text>
                </View>
              )}
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* Dashboard */}
      {onglet === 'dashboard' && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Évolution commissions (kXAF)</Text>
          <LineChart
            data={{ labels: COMMISSIONS_DEMO.map(c => c.mois), datasets: [{ data: COMMISSIONS_DEMO.map(c => c.montant) }] }}
            width={SCREEN_WIDTH - 48} height={180} chartConfig={CHART_CONFIG} bezier
            style={{ borderRadius: 8, marginTop: 8 }}
          />
          <Text style={[styles.sectionTitle, { marginTop: 20 }]}>Productions vs Objectif</Text>
          {PRODUCTIONS_DEMO.map((p, i) => (
            <View key={i} style={styles.progressRow}>
              <Text style={styles.progressLabel}>{p.branche}</Text>
              <View style={styles.progressBar}>
                <View style={[styles.progressFill, { width: `${(p.primes / p.objectif) * 100}%`, backgroundColor: p.primes >= p.objectif ? '#10b981' : '#3b82f6' }]} />
              </View>
              <Text style={styles.progressValue}>{p.primes}M/{p.objectif}M</Text>
            </View>
          ))}
        </View>
      )}

      {/* Portail Courtier */}
      {onglet === 'portail' && (
        <View style={styles.section}>
          <PortailCourtier onEnvoi={(d) => { setDocuments(prev => [d, ...prev]); setOnglet('documents') }} />
        </View>
      )}

      {/* Documents reçus */}
      {onglet === 'documents' && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Documents reçus des courtiers</Text>
          <DocumentsRecus
            documents={documents}
            onUpdate={(d) => setDocuments(prev => prev.map(dd => dd.id === d.id ? d : dd))}
          />
        </View>
      )}

      {/* Commissions */}
      {onglet === 'commissions' && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Commissions mensuelles (kXAF)</Text>
          <BarChart
            data={{ labels: COMMISSIONS_DEMO.map(c => c.mois), datasets: [{ data: COMMISSIONS_DEMO.map(c => c.montant) }] }}
            width={SCREEN_WIDTH - 48} height={200}
            chartConfig={{ ...CHART_CONFIG, color: (o = 1) => `rgba(16, 185, 129, ${o})` }}
            style={{ borderRadius: 8, marginTop: 8 }}
            showValuesOnTopOfBars fromZero yAxisLabel="" yAxisSuffix="k"
          />
          <View style={styles.commissionSummary}>
            <View style={styles.commissionItem}>
              <Text style={styles.commissionLabel}>Total T1 2026</Text>
              <Text style={styles.commissionValue}>7 210 000 XAF</Text>
            </View>
            <View style={styles.commissionItem}>
              <Text style={styles.commissionLabel}>Taux moyen</Text>
              <Text style={styles.commissionValue}>11.2%</Text>
            </View>
            <View style={styles.commissionItem}>
              <Text style={styles.commissionLabel}>Commission en attente</Text>
              <Text style={[styles.commissionValue, { color: '#f59e0b' }]}>940 000 XAF</Text>
            </View>
          </View>
          <TouchableOpacity style={styles.exportBtn}>
            <Ionicons name="download-outline" size={16} color="#1d4ed8" />
            <Text style={styles.exportBtnText}>Exporter rapport courtier</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f1f5f9' },
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', padding: 12, gap: 12 },
  kpiCard: { width: (SCREEN_WIDTH - 48) / 2, backgroundColor: '#fff', borderRadius: 12, padding: 12, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, elevation: 2 },
  kpiIcon: { width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  kpiValue: { fontSize: 15, fontWeight: 'bold', color: '#1e293b' },
  kpiLabel: { fontSize: 11, color: '#64748b', marginTop: 2 },
  kpiVariation: { fontSize: 11, fontWeight: '600', marginTop: 4 },
  tabsScroll: { marginHorizontal: 12, marginBottom: 0 },
  tabs: { flexDirection: 'row', backgroundColor: '#fff', borderRadius: 10, padding: 4 },
  tab: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 8, position: 'relative' },
  tabActive: { backgroundColor: '#eff6ff' },
  tabText: { fontSize: 12, color: '#64748b', fontWeight: '500' },
  tabTextActive: { color: '#1d4ed8', fontWeight: '700' },
  tabBadge: { position: 'absolute', top: 2, right: 2, backgroundColor: '#f59e0b', borderRadius: 8, minWidth: 16, height: 16, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 3 },
  tabBadgeText: { fontSize: 9, color: '#fff', fontWeight: 'bold' },
  section: { backgroundColor: '#fff', borderRadius: 12, margin: 12, padding: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, elevation: 2 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#1e293b', marginBottom: 4 },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  progressLabel: { width: 45, fontSize: 12, color: '#374151', fontWeight: '600' },
  progressBar: { flex: 1, height: 8, backgroundColor: '#f1f5f9', borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: 8, borderRadius: 4 },
  progressValue: { width: 75, fontSize: 11, color: '#64748b', textAlign: 'right' },
  commissionSummary: { marginTop: 16, gap: 10 },
  commissionItem: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  commissionLabel: { fontSize: 13, color: '#64748b' },
  commissionValue: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  exportBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 16, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: '#bfdbfe', backgroundColor: '#eff6ff' },
  exportBtnText: { fontSize: 13, color: '#1d4ed8', fontWeight: '600' },
  // Portail Courtier
  portailContainer: { gap: 12 },
  infoBox: { flexDirection: 'row', gap: 8, backgroundColor: '#eff6ff', borderRadius: 10, padding: 12, alignItems: 'flex-start' },
  infoText: { flex: 1, fontSize: 12, color: '#1e40af', lineHeight: 18 },
  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#374151', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: '#1e293b', backgroundColor: '#fff' },
  catRow: { flexDirection: 'row', gap: 8 },
  catBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: '#d1d5db', backgroundColor: '#f8fafc' },
  catBtnActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  catBtnText: { fontSize: 11, color: '#64748b', fontWeight: '500' },
  catBtnTextActive: { color: '#fff', fontWeight: '700' },
  typeDocList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  typeDocBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20, borderWidth: 1, borderColor: '#d1d5db', backgroundColor: '#f8fafc' },
  typeDocBtnActive: { backgroundColor: '#dbeafe', borderColor: '#3b82f6' },
  typeDocText: { fontSize: 11, color: '#64748b' },
  typeDocTextActive: { color: '#1d4ed8', fontWeight: '600' },
  uploadRow: { flexDirection: 'row', gap: 10 },
  uploadBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: '#bfdbfe', backgroundColor: '#eff6ff' },
  uploadBtnText: { fontSize: 13, color: '#1d4ed8', fontWeight: '600' },
  fichierPreview: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#f0fdf4', borderRadius: 8, padding: 10 },
  fichierNom: { flex: 1, fontSize: 12, color: '#166534' },
  submitBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1d4ed8', paddingVertical: 14, borderRadius: 12 },
  submitBtnDisabled: { backgroundColor: '#94a3b8' },
  submitBtnText: { fontSize: 14, fontWeight: '700', color: '#fff' },
  succesContainer: { alignItems: 'center', paddingVertical: 32, gap: 12 },
  succesIcon: { width: 80, height: 80, borderRadius: 40, backgroundColor: '#dcfce7', alignItems: 'center', justifyContent: 'center' },
  succesTitle: { fontSize: 18, fontWeight: 'bold', color: '#1e293b' },
  succesText: { fontSize: 13, color: '#64748b', textAlign: 'center', paddingHorizontal: 16, lineHeight: 20 },
  succesBtn: { backgroundColor: '#1d4ed8', paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 },
  succesBtnText: { fontSize: 13, color: '#fff', fontWeight: '600' },
  // Documents reçus
  alerteBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#fef3c7', borderRadius: 8, padding: 10, marginBottom: 12 },
  alerteBannerText: { fontSize: 12, color: '#92400e', fontWeight: '500' },
  docCard: { borderWidth: 1, borderColor: '#e2e8f0', borderRadius: 10, padding: 12, marginBottom: 10, backgroundColor: '#fff' },
  docCardValide: { borderColor: '#bbf7d0' },
  docCardRejete: { borderColor: '#fecaca' },
  docHeader: { flexDirection: 'row', alignItems: 'flex-start' },
  docCatIcon: { width: 36, height: 36, borderRadius: 8, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  docCourtier: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  docMeta: { fontSize: 11, color: '#64748b', marginTop: 2 },
  docFichier: { fontSize: 10, color: '#94a3b8', marginTop: 1 },
  docStatutBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 10, backgroundColor: '#f1f5f9' },
  docStatutText: { fontSize: 10, fontWeight: '600' },
  scoreRow: { borderRadius: 6, padding: 6, marginTop: 8 },
  scoreText: { fontSize: 11, fontWeight: '700' },
  docActions: { flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' },
  actionBtnPrimary: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#1d4ed8', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  actionBtnGreen: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#16a34a', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  actionBtnRed: { flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderColor: '#fca5a5', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  actionBtnText: { fontSize: 11, color: '#fff', fontWeight: '600' },
  valideLabel: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  valideLabelText: { fontSize: 12, color: '#16a34a', fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingVertical: 40, gap: 8 },
  emptyStateText: { fontSize: 13, color: '#94a3b8' },
})
