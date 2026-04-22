/**
 * YukpoAssurance — Écran mobile RH
 * Dématérialisation : documents employés, demandes RH dématérialisées
 * KPI Performance : classement transparent, scores, badges
 */
import { useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Modal, Alert, Dimensions, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'

const SCREEN_W = Dimensions.get('window').width

// ─── Types ────────────────────────────────────────────────────────────────────

type ModeVue = 'employe' | 'rh'
type OngletRH = 'documents' | 'demandes' | 'kpi'

interface DocRH {
  id: string
  employe_nom: string
  employe_id: string
  type: 'contrat' | 'bulletin_paie' | 'attestation' | 'conge' | 'formation' | 'certificat'
  periode: string
  date_upload: string
  statut: 'disponible' | 'en_traitement' | 'archive'
}

interface DemandeRH {
  id: string
  employe_nom: string
  type: string
  description: string
  date_demande: string
  date_debut?: string
  date_fin?: string
  statut: 'en_attente' | 'approuve' | 'refuse'
  commentaire_rh?: string
}

// Employé actuellement connecté (en prod : issu du JWT)
const MOI_ID = 'EMP-001'
const MOI_NOM = 'Kouassi Jean-Baptiste'
const MOI_DEPT = 'Technique'
const MOI_RESPONSABLE = 'Coulibaly Seydou'

interface KpiEmploye {
  employe_id: string
  employe_nom: string
  departement: string
  score_global: number
  score_qualite: number
  score_reactivite: number
  score_volume: number
  score_objectifs: number
  sinistres_traites: number
  contrats_emis: number
  documents_scannes: number
  reponse_moyenne_heures: number
  taux_completion_objectifs: number
  objectif_mensuel: number
  realise_mensuel: number
  badges: string[]
  historique_scores: { mois: string; score: number }[]
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const DOCS_DEMO: DocRH[] = [
  { id: 'D1', employe_nom: 'Kouassi Jean-Baptiste', employe_id: 'EMP-001', type: 'bulletin_paie', periode: 'Mars 2026', date_upload: '2026-04-05', statut: 'disponible' },
  { id: 'D2', employe_nom: 'Kouassi Jean-Baptiste', employe_id: 'EMP-001', type: 'contrat', periode: 'CDI 2023', date_upload: '2023-01-15', statut: 'disponible' },
  { id: 'D3', employe_nom: 'Traoré Fatoumata', employe_id: 'EMP-002', type: 'bulletin_paie', periode: 'Mars 2026', date_upload: '2026-04-05', statut: 'disponible' },
  { id: 'D4', employe_nom: 'Traoré Fatoumata', employe_id: 'EMP-002', type: 'attestation', periode: 'Avr 2026', date_upload: '2026-04-09', statut: 'en_traitement' },
  { id: 'D5', employe_nom: 'Diallo Ibrahim', employe_id: 'EMP-003', type: 'formation', periode: 'Q1 2026', date_upload: '2026-03-30', statut: 'disponible' },
  { id: 'D6', employe_nom: 'Coulibaly Seydou', employe_id: 'EMP-005', type: 'conge', periode: 'Avr 2026', date_upload: '2026-04-06', statut: 'disponible' },
  { id: 'D7', employe_nom: 'Bamba Koffi', employe_id: 'EMP-004', type: 'certificat', periode: 'Avr 2026', date_upload: '2026-04-08', statut: 'archive' },
  { id: 'D8', employe_nom: 'Ouattara Marie', employe_id: 'EMP-006', type: 'bulletin_paie', periode: 'Mars 2026', date_upload: '2026-04-05', statut: 'disponible' },
]

const DEMANDES_DEMO: DemandeRH[] = [
  { id: 'DEM-001', employe_nom: 'Traoré Fatoumata', type: 'conge', description: 'Congé annuel — 15 jours', date_demande: '2026-04-08', date_debut: '2026-04-21', date_fin: '2026-05-05', statut: 'en_attente' },
  { id: 'DEM-002', employe_nom: 'Diallo Ibrahim', type: 'attestation', description: 'Attestation de travail pour dossier bancaire', date_demande: '2026-04-09', statut: 'approuve', commentaire_rh: 'Document généré et remis.' },
  { id: 'DEM-003', employe_nom: 'Coulibaly Seydou', type: 'formation', description: 'Formation LLM Fine-tuning (3 jours)', date_demande: '2026-04-05', date_debut: '2026-04-28', date_fin: '2026-04-30', statut: 'approuve', commentaire_rh: 'Approuvé — budget IT disponible.' },
  { id: 'DEM-004', employe_nom: 'Kouassi Jean-Baptiste', type: 'avance', description: 'Avance sur salaire 150 000 XAF — urgence familiale', date_demande: '2026-04-07', statut: 'en_attente' },
]

const KPI_DEMO: KpiEmploye[] = [
  {
    employe_id: 'EMP-005', employe_nom: 'Coulibaly Seydou', departement: 'Digital',
    score_global: 95, score_qualite: 98, score_reactivite: 96, score_volume: 92, score_objectifs: 94,
    sinistres_traites: 0, contrats_emis: 0, documents_scannes: 142, reponse_moyenne_heures: 0.8, taux_completion_objectifs: 0.98,
    objectif_mensuel: 100, realise_mensuel: 98,
    badges: ['🏆 Top performer', '⚡ Réactivité', '🤖 IA Expert'],
    historique_scores: [
      { mois: 'Nov', score: 88 }, { mois: 'Déc', score: 90 }, { mois: 'Jan', score: 91 },
      { mois: 'Fév', score: 93 }, { mois: 'Mar', score: 95 },
    ],
  },
  {
    employe_id: 'EMP-001', employe_nom: 'Kouassi Jean-Baptiste', departement: 'Technique',
    score_global: 91, score_qualite: 94, score_reactivite: 89, score_volume: 88, score_objectifs: 93,
    sinistres_traites: 18, contrats_emis: 4, documents_scannes: 56, reponse_moyenne_heures: 1.2, taux_completion_objectifs: 0.95,
    objectif_mensuel: 20, realise_mensuel: 18,
    badges: ['🥇 Expert sinistres', '📋 Rigueur'],
    historique_scores: [
      { mois: 'Nov', score: 85 }, { mois: 'Déc', score: 87 }, { mois: 'Jan', score: 88 },
      { mois: 'Fév', score: 90 }, { mois: 'Mar', score: 91 },
    ],
  },
  {
    employe_id: 'EMP-002', employe_nom: 'Traoré Fatoumata', departement: 'Sinistres',
    score_global: 87, score_qualite: 90, score_reactivite: 85, score_volume: 88, score_objectifs: 86,
    sinistres_traites: 34, contrats_emis: 0, documents_scannes: 89, reponse_moyenne_heures: 1.5, taux_completion_objectifs: 0.92,
    objectif_mensuel: 35, realise_mensuel: 34,
    badges: ['🛡️ Sinistres Pro'],
    historique_scores: [
      { mois: 'Nov', score: 80 }, { mois: 'Déc', score: 82 }, { mois: 'Jan', score: 83 },
      { mois: 'Fév', score: 85 }, { mois: 'Mar', score: 87 },
    ],
  },
  {
    employe_id: 'EMP-003', employe_nom: 'Diallo Ibrahim', departement: 'Commercial',
    score_global: 82, score_qualite: 85, score_reactivite: 80, score_volume: 82, score_objectifs: 81,
    sinistres_traites: 0, contrats_emis: 22, documents_scannes: 45, reponse_moyenne_heures: 2.1, taux_completion_objectifs: 0.88,
    objectif_mensuel: 25, realise_mensuel: 22,
    badges: ['💼 Commercial'],
    historique_scores: [
      { mois: 'Nov', score: 76 }, { mois: 'Déc', score: 78 }, { mois: 'Jan', score: 80 },
      { mois: 'Fév', score: 81 }, { mois: 'Mar', score: 82 },
    ],
  },
  {
    employe_id: 'EMP-004', employe_nom: 'Bamba Koffi', departement: 'Comptabilité',
    score_global: 78, score_qualite: 82, score_reactivite: 75, score_volume: 76, score_objectifs: 79,
    sinistres_traites: 0, contrats_emis: 0, documents_scannes: 67, reponse_moyenne_heures: 2.5, taux_completion_objectifs: 0.83,
    objectif_mensuel: 80, realise_mensuel: 66,
    badges: ['📊 Comptable'],
    historique_scores: [
      { mois: 'Nov', score: 73 }, { mois: 'Déc', score: 74 }, { mois: 'Jan', score: 75 },
      { mois: 'Fév', score: 77 }, { mois: 'Mar', score: 78 },
    ],
  },
  {
    employe_id: 'EMP-006', employe_nom: 'Ouattara Marie', departement: 'RH',
    score_global: 74, score_qualite: 78, score_reactivite: 72, score_volume: 70, score_objectifs: 76,
    sinistres_traites: 0, contrats_emis: 0, documents_scannes: 38, reponse_moyenne_heures: 3.0, taux_completion_objectifs: 0.80,
    objectif_mensuel: 40, realise_mensuel: 32,
    badges: [],
    historique_scores: [
      { mois: 'Nov', score: 70 }, { mois: 'Déc', score: 71 }, { mois: 'Jan', score: 72 },
      { mois: 'Fév', score: 73 }, { mois: 'Mar', score: 74 },
    ],
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

const TYPE_DOC_CONFIG: Record<string, { label: string; icon: string; couleur: string }> = {
  contrat:      { label: 'Contrat',       icon: 'document-text-outline', couleur: '#1d4ed8' },
  bulletin_paie:{ label: 'Bulletin paie', icon: 'cash-outline',           couleur: '#059669' },
  attestation:  { label: 'Attestation',   icon: 'ribbon-outline',         couleur: '#7c3aed' },
  conge:        { label: 'Congé',         icon: 'calendar-outline',       couleur: '#d97706' },
  formation:    { label: 'Formation',     icon: 'school-outline',         couleur: '#0891b2' },
  certificat:   { label: 'Certificat',    icon: 'medal-outline',          couleur: '#be185d' },
}

const STATUT_DOC: Record<string, { label: string; bg: string; txt: string }> = {
  disponible:    { label: 'Disponible',     bg: '#dcfce7', txt: '#15803d' },
  en_traitement: { label: 'En traitement',  bg: '#fef3c7', txt: '#92400e' },
  archive:       { label: 'Archivé',        bg: '#f1f5f9', txt: '#475569' },
}

const STATUT_DEM: Record<string, { label: string; bg: string; txt: string; icon: string }> = {
  en_attente: { label: 'En attente', bg: '#fef3c7', txt: '#92400e', icon: 'time-outline' },
  approuve:   { label: 'Approuvé',   bg: '#dcfce7', txt: '#15803d', icon: 'checkmark-circle-outline' },
  refuse:     { label: 'Refusé',     bg: '#fee2e2', txt: '#dc2626', icon: 'close-circle-outline' },
}

const TYPE_DEM_LABELS: Record<string, string> = {
  conge: 'Congé', attestation: 'Attestation', avance: 'Avance', formation: 'Formation',
  certificat: 'Certificat', autre: 'Autre',
}

function scoreColor(s: number) {
  if (s >= 90) return '#16a34a'
  if (s >= 75) return '#2563eb'
  if (s >= 60) return '#d97706'
  return '#dc2626'
}

function initiales(nom: string) {
  return nom.split(' ').slice(0, 2).map(p => p[0]).join('').toUpperCase()
}

// ─── Composant mini barre de score ───────────────────────────────────────────

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <View style={{ marginBottom: 8 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
        <Text style={{ fontSize: 12, color: '#64748b' }}>{label}</Text>
        <Text style={{ fontSize: 12, fontWeight: '700', color: scoreColor(value) }}>{value}</Text>
      </View>
      <View style={{ height: 6, backgroundColor: '#e2e8f0', borderRadius: 3 }}>
        <View style={{ height: 6, width: `${value}%`, backgroundColor: scoreColor(value), borderRadius: 3 }} />
      </View>
    </View>
  )
}

// ─── Mini sparkline (graphique historique simple) ────────────────────────────

function MiniSparkline({ data }: { data: { mois: string; score: number }[] }) {
  const max = Math.max(...data.map(d => d.score))
  const min = Math.min(...data.map(d => d.score))
  const range = max - min || 1
  const W = SCREEN_W - 80
  const H = 40
  const barW = (W - (data.length - 1) * 4) / data.length

  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: H, gap: 4 }}>
        {data.map((d, i) => {
          const barH = Math.max(8, ((d.score - min) / range) * (H - 8) + 8)
          const isLast = i === data.length - 1
          return (
            <View key={i} style={{ alignItems: 'center', flex: 1 }}>
              <View style={{
                width: barW, height: barH,
                backgroundColor: isLast ? '#1d4ed8' : '#bfdbfe',
                borderRadius: 3,
              }} />
            </View>
          )
        })}
      </View>
      <View style={{ flexDirection: 'row', gap: 4, marginTop: 4 }}>
        {data.map((d, i) => (
          <Text key={i} style={{ flex: 1, fontSize: 9, color: '#94a3b8', textAlign: 'center' }}>{d.mois}</Text>
        ))}
      </View>
    </View>
  )
}

// ─── Onglet Documents ─────────────────────────────────────────────────────────

function OngletDocuments() {
  const [filtre, setFiltre] = useState<string>('tous')
  const [recherche, setRecherche] = useState('')

  const filtres = [
    { id: 'tous', label: 'Tous' },
    { id: 'bulletin_paie', label: 'Bulletins' },
    { id: 'contrat', label: 'Contrats' },
    { id: 'attestation', label: 'Attestations' },
    { id: 'conge', label: 'Congés' },
  ]

  const docs = DOCS_DEMO.filter(d => {
    if (filtre !== 'tous' && d.type !== filtre) return false
    if (recherche && !d.employe_nom.toLowerCase().includes(recherche.toLowerCase()) && !d.periode.toLowerCase().includes(recherche.toLowerCase())) return false
    return true
  })

  return (
    <View style={{ flex: 1 }}>
      {/* Barre de recherche */}
      <View style={s.searchBar}>
        <Ionicons name="search-outline" size={16} color="#94a3b8" />
        <TextInput
          style={s.searchInput}
          placeholder="Rechercher un document..."
          value={recherche}
          onChangeText={setRecherche}
          placeholderTextColor="#94a3b8"
        />
      </View>

      {/* Filtres types */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ paddingHorizontal: 12, marginBottom: 8 }} contentContainerStyle={{ gap: 8 }}>
        {filtres.map(f => (
          <TouchableOpacity
            key={f.id}
            onPress={() => setFiltre(f.id)}
            style={[s.chip, filtre === f.id && s.chipActive]}
          >
            <Text style={[s.chipText, filtre === f.id && s.chipTextActive]}>{f.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={{ padding: 12, gap: 10 }}>
        {docs.map(doc => {
          const cfg = TYPE_DOC_CONFIG[doc.type]
          const statut = STATUT_DOC[doc.statut]
          return (
            <View key={doc.id} style={s.card}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <View style={[s.docIcon, { backgroundColor: cfg.couleur + '18' }]}>
                  <Ionicons name={cfg.icon as never} size={20} color={cfg.couleur} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>{cfg.label} — {doc.periode}</Text>
                  <Text style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>{doc.employe_nom}</Text>
                  <Text style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>Déposé le {doc.date_upload}</Text>
                </View>
                <View style={[s.badge, { backgroundColor: statut.bg }]}>
                  <Text style={[s.badgeTxt, { color: statut.txt }]}>{statut.label}</Text>
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity
                  style={[s.btnSm, { backgroundColor: '#eff6ff', flex: 1 }]}
                  onPress={() => Alert.alert('Téléchargement', `Document ${cfg.label} en cours de téléchargement...`)}
                >
                  <Ionicons name="download-outline" size={14} color="#1d4ed8" />
                  <Text style={{ fontSize: 12, color: '#1d4ed8', fontWeight: '600' }}>Télécharger</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.btnSm, { backgroundColor: '#f1f5f9', flex: 1 }]}
                  onPress={() => Alert.alert('Aperçu', `Aperçu du document ${cfg.label}`)}
                >
                  <Ionicons name="eye-outline" size={14} color="#475569" />
                  <Text style={{ fontSize: 12, color: '#475569', fontWeight: '600' }}>Aperçu</Text>
                </TouchableOpacity>
              </View>
            </View>
          )
        })}

        {docs.length === 0 && (
          <View style={s.empty}>
            <Ionicons name="folder-open-outline" size={40} color="#cbd5e1" />
            <Text style={s.emptyTxt}>Aucun document trouvé</Text>
          </View>
        )}
      </ScrollView>
    </View>
  )
}

// ─── Onglet Demandes RH ───────────────────────────────────────────────────────

function OngletDemandes() {
  const [demandes, setDemandes] = useState<DemandeRH[]>(DEMANDES_DEMO)
  const [filtre, setFiltre] = useState<'tous' | 'en_attente' | 'approuve' | 'refuse'>('tous')
  const [modalNouvelle, setModalNouvelle] = useState(false)
  const [type, setType] = useState('conge')
  const [description, setDescription] = useState('')
  const [dateDebut, setDateDebut] = useState('')
  const [dateFin, setDateFin] = useState('')
  const [envoi, setEnvoi] = useState(false)

  const typesDem = [
    { id: 'conge', label: 'Congé', icon: 'calendar-outline' },
    { id: 'attestation', label: 'Attestation', icon: 'ribbon-outline' },
    { id: 'avance', label: 'Avance', icon: 'cash-outline' },
    { id: 'formation', label: 'Formation', icon: 'school-outline' },
    { id: 'certificat', label: 'Certificat', icon: 'medal-outline' },
    { id: 'autre', label: 'Autre', icon: 'ellipsis-horizontal-outline' },
  ]

  const filtered = demandes.filter(d => filtre === 'tous' || d.statut === filtre)
  const enAttenteCount = demandes.filter(d => d.statut === 'en_attente').length

  const soumettre = async () => {
    if (!description.trim()) { Alert.alert('Erreur', 'Veuillez renseigner une description.'); return }
    setEnvoi(true)
    await new Promise(r => setTimeout(r, 1200))
    const nv: DemandeRH = {
      id: `DEM-${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      employe_nom: 'Moi (connecté)',
      type,
      description,
      date_demande: new Date().toISOString().split('T')[0],
      date_debut: dateDebut || undefined,
      date_fin: dateFin || undefined,
      statut: 'en_attente',
    }
    setDemandes(prev => [nv, ...prev])
    setEnvoi(false)
    setModalNouvelle(false)
    setDescription('')
    setDateDebut('')
    setDateFin('')
    Alert.alert('Demande soumise', 'Votre demande RH a été transmise au service RH.')
  }

  return (
    <View style={{ flex: 1 }}>
      {/* Filtres statut */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ paddingHorizontal: 12, marginBottom: 8 }} contentContainerStyle={{ gap: 8 }}>
        {[
          { id: 'tous', label: 'Toutes' },
          { id: 'en_attente', label: `En attente ${enAttenteCount > 0 ? `(${enAttenteCount})` : ''}` },
          { id: 'approuve', label: 'Approuvées' },
          { id: 'refuse', label: 'Refusées' },
        ].map(f => (
          <TouchableOpacity key={f.id} onPress={() => setFiltre(f.id as never)} style={[s.chip, filtre === f.id && s.chipActive]}>
            <Text style={[s.chipText, filtre === f.id && s.chipTextActive]}>{f.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={{ padding: 12, gap: 10, paddingBottom: 90 }}>
        {filtered.map(dem => {
          const st = STATUT_DEM[dem.statut]
          return (
            <View key={dem.id} style={s.card}>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>
                    {TYPE_DEM_LABELS[dem.type] || dem.type}
                  </Text>
                  <Text style={{ fontSize: 12, color: '#475569', marginTop: 3 }}>{dem.employe_nom}</Text>
                  <Text style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{dem.description}</Text>
                  {(dem.date_debut || dem.date_fin) && (
                    <Text style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                      📅 {dem.date_debut}{dem.date_fin ? ` → ${dem.date_fin}` : ''}
                    </Text>
                  )}
                  {dem.commentaire_rh && (
                    <Text style={{ fontSize: 11, color: '#059669', marginTop: 4, fontStyle: 'italic' }}>
                      💬 {dem.commentaire_rh}
                    </Text>
                  )}
                </View>
                <View>
                  <View style={[s.badge, { backgroundColor: st.bg, alignSelf: 'flex-end' }]}>
                    <Ionicons name={st.icon as never} size={12} color={st.txt} />
                    <Text style={[s.badgeTxt, { color: st.txt }]}>{st.label}</Text>
                  </View>
                  <Text style={{ fontSize: 10, color: '#94a3b8', marginTop: 4, textAlign: 'right' }}>{dem.date_demande}</Text>
                </View>
              </View>
            </View>
          )
        })}

        {filtered.length === 0 && (
          <View style={s.empty}>
            <Ionicons name="document-outline" size={40} color="#cbd5e1" />
            <Text style={s.emptyTxt}>Aucune demande dans cette catégorie</Text>
          </View>
        )}
      </ScrollView>

      {/* FAB Nouvelle demande */}
      <TouchableOpacity style={s.fab} onPress={() => setModalNouvelle(true)}>
        <Ionicons name="add" size={26} color="#fff" />
      </TouchableOpacity>

      {/* Modal nouvelle demande */}
      <Modal visible={modalNouvelle} animationType="slide" presentationStyle="pageSheet">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Nouvelle demande RH</Text>
            <TouchableOpacity onPress={() => setModalNouvelle(false)}>
              <Ionicons name="close" size={24} color="#64748b" />
            </TouchableOpacity>
          </View>
          <ScrollView style={{ padding: 16 }}>
            {/* Type de demande */}
            <Text style={s.fieldLabel}>Type de demande</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {typesDem.map(t => (
                <TouchableOpacity
                  key={t.id}
                  onPress={() => setType(t.id)}
                  style={[s.typeChip, type === t.id && s.typeChipActive]}
                >
                  <Ionicons name={t.icon as never} size={14} color={type === t.id ? '#fff' : '#475569'} />
                  <Text style={[s.typeChipTxt, type === t.id && { color: '#fff' }]}>{t.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Description */}
            <Text style={s.fieldLabel}>Description</Text>
            <TextInput
              style={[s.input, { height: 80, textAlignVertical: 'top' }]}
              multiline
              placeholder="Décrivez votre demande..."
              value={description}
              onChangeText={setDescription}
              placeholderTextColor="#94a3b8"
            />

            {/* Dates (congé / formation) */}
            {(type === 'conge' || type === 'formation') && (
              <>
                <Text style={s.fieldLabel}>Date de début</Text>
                <TextInput
                  style={s.input}
                  placeholder="YYYY-MM-DD"
                  value={dateDebut}
                  onChangeText={setDateDebut}
                  placeholderTextColor="#94a3b8"
                />
                <Text style={s.fieldLabel}>Date de fin</Text>
                <TextInput
                  style={s.input}
                  placeholder="YYYY-MM-DD"
                  value={dateFin}
                  onChangeText={setDateFin}
                  placeholderTextColor="#94a3b8"
                />
              </>
            )}

            <TouchableOpacity style={[s.btnPrimary, envoi && { opacity: 0.6 }]} onPress={soumettre} disabled={envoi}>
              {envoi ? <ActivityIndicator color="#fff" size="small" /> : (
                <>
                  <Ionicons name="send-outline" size={16} color="#fff" />
                  <Text style={{ color: '#fff', fontWeight: '700', fontSize: 15 }}>Soumettre la demande</Text>
                </>
              )}
            </TouchableOpacity>
          </ScrollView>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  )
}

// ─── Onglet KPI Performance ───────────────────────────────────────────────────

function OngletKPI() {
  const [selected, setSelected] = useState<KpiEmploye | null>(null)

  return (
    <View style={{ flex: 1 }}>
      {/* Bannière transparence */}
      <View style={s.infoBanner}>
        <Ionicons name="information-circle-outline" size={16} color="#1d4ed8" />
        <Text style={s.infoBannerTxt}>
          Scores calculés automatiquement à partir des actions réelles sur la plateforme. Transparence totale.
        </Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 12, gap: 10, paddingBottom: 30 }}>
        {/* Classement */}
        {KPI_DEMO.map((emp, idx) => (
          <TouchableOpacity key={emp.employe_id} style={s.card} onPress={() => setSelected(emp)}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              {/* Rang */}
              <View style={[s.rang, idx < 3 && { backgroundColor: idx === 0 ? '#fef3c7' : idx === 1 ? '#f1f5f9' : '#fde8d0' }]}>
                <Text style={{ fontSize: 14, fontWeight: '800', color: idx === 0 ? '#d97706' : idx === 1 ? '#475569' : '#c2410c' }}>
                  {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `#${idx + 1}`}
                </Text>
              </View>
              {/* Avatar */}
              <View style={[s.avatar, { backgroundColor: scoreColor(emp.score_global) + '25' }]}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: scoreColor(emp.score_global) }}>{initiales(emp.employe_nom)}</Text>
              </View>
              {/* Infos */}
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>{emp.employe_nom}</Text>
                <Text style={{ fontSize: 11, color: '#64748b' }}>{emp.departement}</Text>
                {emp.badges.length > 0 && (
                  <Text style={{ fontSize: 10, color: '#7c3aed', marginTop: 2 }}>{emp.badges[0]}</Text>
                )}
              </View>
              {/* Score */}
              <View style={{ alignItems: 'center' }}>
                <Text style={{ fontSize: 22, fontWeight: '800', color: scoreColor(emp.score_global) }}>{emp.score_global}</Text>
                <Text style={{ fontSize: 10, color: '#94a3b8' }}>/100</Text>
              </View>
            </View>
            {/* Barre score global */}
            <View style={{ height: 5, backgroundColor: '#e2e8f0', borderRadius: 3, marginTop: 10 }}>
              <View style={{ height: 5, width: `${emp.score_global}%`, backgroundColor: scoreColor(emp.score_global), borderRadius: 3 }} />
            </View>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Modal détail employé */}
      <Modal visible={!!selected} animationType="slide" presentationStyle="pageSheet">
        {selected && (
          <View style={{ flex: 1, backgroundColor: '#f1f5f9' }}>
            <View style={s.modalHeader}>
              <View style={{ flex: 1 }}>
                <Text style={s.modalTitle}>{selected.employe_nom}</Text>
                <Text style={{ fontSize: 12, color: '#64748b' }}>{selected.departement}</Text>
              </View>
              <TouchableOpacity onPress={() => setSelected(null)}>
                <Ionicons name="close" size={24} color="#64748b" />
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
              {/* Score global */}
              <View style={[s.card, { alignItems: 'center', paddingVertical: 20 }]}>
                <Text style={{ fontSize: 48, fontWeight: '800', color: scoreColor(selected.score_global) }}>
                  {selected.score_global}
                </Text>
                <Text style={{ fontSize: 14, color: '#64748b', marginTop: 4 }}>Score global de performance</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12, justifyContent: 'center' }}>
                  {selected.badges.map((b, i) => (
                    <View key={i} style={{ backgroundColor: '#ede9fe', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 }}>
                      <Text style={{ fontSize: 11, color: '#7c3aed', fontWeight: '600' }}>{b}</Text>
                    </View>
                  ))}
                  {selected.badges.length === 0 && (
                    <Text style={{ fontSize: 11, color: '#94a3b8' }}>Aucun badge ce mois</Text>
                  )}
                </View>
              </View>

              {/* Axes de score */}
              <View style={s.card}>
                <Text style={s.cardTitle}>Axes de performance</Text>
                <View style={{ marginTop: 8 }}>
                  <ScoreBar label="Qualité" value={selected.score_qualite} />
                  <ScoreBar label="Réactivité" value={selected.score_reactivite} />
                  <ScoreBar label="Volume" value={selected.score_volume} />
                  <ScoreBar label="Objectifs" value={selected.score_objectifs} />
                </View>
              </View>

              {/* Métriques sources */}
              <View style={s.card}>
                <Text style={s.cardTitle}>Sources de données</Text>
                <Text style={{ fontSize: 11, color: '#94a3b8', marginBottom: 10 }}>Mesures extraites automatiquement de la plateforme</Text>
                {[
                  { label: 'Sinistres traités', value: selected.sinistres_traites, icon: 'shield-outline' },
                  { label: 'Contrats émis', value: selected.contrats_emis, icon: 'document-text-outline' },
                  { label: 'Documents scannés', value: selected.documents_scannes, icon: 'scan-outline' },
                  { label: 'Réponse moy. (h)', value: selected.reponse_moyenne_heures.toFixed(1), icon: 'timer-outline' },
                  { label: 'Taux objectifs', value: `${(selected.taux_completion_objectifs * 100).toFixed(0)}%`, icon: 'checkmark-circle-outline' },
                ].map((m, i) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: i < 4 ? 1 : 0, borderBottomColor: '#f1f5f9' }}>
                    <Ionicons name={m.icon as never} size={14} color="#94a3b8" />
                    <Text style={{ flex: 1, fontSize: 12, color: '#475569', marginLeft: 8 }}>{m.label}</Text>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>{m.value}</Text>
                  </View>
                ))}
              </View>

              {/* Objectif mensuel */}
              <View style={s.card}>
                <Text style={s.cardTitle}>Objectif mensuel</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8, marginBottom: 6 }}>
                  <Text style={{ fontSize: 12, color: '#64748b' }}>{selected.realise_mensuel} / {selected.objectif_mensuel}</Text>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: scoreColor(selected.score_global) }}>
                    {Math.round(selected.realise_mensuel / selected.objectif_mensuel * 100)}%
                  </Text>
                </View>
                <View style={{ height: 10, backgroundColor: '#e2e8f0', borderRadius: 5 }}>
                  <View style={{
                    height: 10,
                    width: `${Math.min(100, selected.realise_mensuel / selected.objectif_mensuel * 100)}%`,
                    backgroundColor: scoreColor(selected.score_global),
                    borderRadius: 5,
                  }} />
                </View>
              </View>

              {/* Évolution historique */}
              <View style={s.card}>
                <Text style={s.cardTitle}>Évolution (5 mois)</Text>
                <View style={{ marginTop: 12 }}>
                  <MiniSparkline data={selected.historique_scores} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 }}>
                  <Text style={{ fontSize: 11, color: '#94a3b8' }}>
                    Min : <Text style={{ fontWeight: '700', color: '#ef4444' }}>{Math.min(...selected.historique_scores.map(h => h.score))}</Text>
                  </Text>
                  <Text style={{ fontSize: 11, color: '#94a3b8' }}>
                    Max : <Text style={{ fontWeight: '700', color: '#16a34a' }}>{Math.max(...selected.historique_scores.map(h => h.score))}</Text>
                  </Text>
                  <Text style={{ fontSize: 11, color: '#94a3b8' }}>
                    Tendance : <Text style={{ fontWeight: '700', color: '#1d4ed8' }}>
                      {selected.historique_scores[selected.historique_scores.length - 1].score > selected.historique_scores[0].score ? '↑' : '→'}
                    </Text>
                  </Text>
                </View>
              </View>
            </ScrollView>
          </View>
        )}
      </Modal>
    </View>
  )
}

// ─── Portail Employé ─────────────────────────────────────────────────────────

function PortailEmploye() {
  const [modalDemande, setModalDemande] = useState(false)
  const [type, setType] = useState('conge')
  const [description, setDescription] = useState('')
  const [dateDebut, setDateDebut] = useState('')
  const [dateFin, setDateFin] = useState('')
  const [envoi, setEnvoi] = useState(false)
  const [messDemandes, setMesDemandes] = useState<DemandeRH[]>(
    DEMANDES_DEMO.filter(d => d.employe_nom === MOI_NOM || d.id === 'DEM-001' || d.id === 'DEM-004')
  )

  const typesDem = [
    { id: 'conge', label: 'Congé', icon: 'calendar-outline', couleur: '#d97706' },
    { id: 'attestation', label: 'Attestation', icon: 'ribbon-outline', couleur: '#7c3aed' },
    { id: 'avance', label: 'Avance', icon: 'cash-outline', couleur: '#059669' },
    { id: 'formation', label: 'Formation', icon: 'school-outline', couleur: '#0891b2' },
    { id: 'certificat', label: 'Certificat', icon: 'medal-outline', couleur: '#be185d' },
    { id: 'autre', label: 'Autre', icon: 'ellipsis-horizontal-outline', couleur: '#64748b' },
  ]

  const mesDocs = DOCS_DEMO.filter(d => d.employe_id === MOI_ID)

  const soumettre = async () => {
    if (!description.trim()) { Alert.alert('Erreur', 'Veuillez renseigner une description.'); return }
    setEnvoi(true)
    await new Promise(r => setTimeout(r, 1200))
    const nv: DemandeRH = {
      id: `DEM-${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      employe_nom: MOI_NOM,
      type,
      description,
      date_demande: new Date().toISOString().split('T')[0],
      date_debut: dateDebut || undefined,
      date_fin: dateFin || undefined,
      statut: 'en_attente',
    }
    setMesDemandes(prev => [nv, ...prev])
    setEnvoi(false)
    setModalDemande(false)
    setDescription('')
    setDateDebut('')
    setDateFin('')
    Alert.alert('Demande soumise ✓', `Votre demande a été transmise.\n\nCircuit : ${MOI_NOM} → ${MOI_RESPONSABLE} (N+1) → Service RH`)
  }

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
      {/* Carte profil */}
      <View style={[s.card, { margin: 12, flexDirection: 'row', alignItems: 'center', gap: 14 }]}>
        <View style={[s.avatar, { width: 50, height: 50, borderRadius: 25, backgroundColor: '#dbeafe' }]}>
          <Text style={{ fontSize: 16, fontWeight: '800', color: '#1d4ed8' }}>{initiales(MOI_NOM)}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: '700', color: '#1e293b' }}>{MOI_NOM}</Text>
          <Text style={{ fontSize: 12, color: '#64748b' }}>{MOI_DEPT} · {MOI_ID}</Text>
          <Text style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>N+1 : {MOI_RESPONSABLE}</Text>
        </View>
        <View style={[s.badge, { backgroundColor: '#dcfce7' }]}>
          <Text style={[s.badgeTxt, { color: '#15803d' }]}>Actif</Text>
        </View>
      </View>

      {/* Circuit de validation */}
      <View style={{ marginHorizontal: 12, marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#eff6ff', borderRadius: 10, padding: 12, gap: 6 }}>
          <Ionicons name="git-branch-outline" size={16} color="#1d4ed8" />
          <Text style={{ fontSize: 11, color: '#1d4ed8', fontWeight: '600', flex: 1 }}>
            Circuit : Moi → {MOI_RESPONSABLE} (N+1) → Service RH
          </Text>
        </View>
      </View>

      {/* Actions rapides */}
      <View style={[s.card, { margin: 12, marginTop: 0 }]}>
        <Text style={s.cardTitle}>Actions rapides</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
          {typesDem.map(t => (
            <TouchableOpacity
              key={t.id}
              style={{ width: (SCREEN_W - 80) / 3, alignItems: 'center', gap: 6 }}
              onPress={() => { setType(t.id); setModalDemande(true) }}
            >
              <View style={{ width: 46, height: 46, borderRadius: 12, backgroundColor: t.couleur + '18', alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={t.icon as never} size={20} color={t.couleur} />
              </View>
              <Text style={{ fontSize: 11, color: '#374151', fontWeight: '600', textAlign: 'center' }}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Mes demandes en cours */}
      <View style={[s.card, { margin: 12, marginTop: 0 }]}>
        <Text style={s.cardTitle}>Mes demandes</Text>
        {messDemandes.length === 0 && (
          <Text style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>Aucune demande</Text>
        )}
        {messDemandes.map(dem => {
          const st = STATUT_DEM[dem.statut]
          return (
            <View key={dem.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' }}>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: '#1e293b' }}>
                    {TYPE_DEM_LABELS[dem.type] || dem.type}
                  </Text>
                  <Text style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{dem.description}</Text>
                  {dem.commentaire_rh && (
                    <Text style={{ fontSize: 11, color: '#059669', marginTop: 3, fontStyle: 'italic' }}>
                      💬 {dem.commentaire_rh}
                    </Text>
                  )}
                </View>
                <View style={[s.badge, { backgroundColor: st.bg }]}>
                  <Ionicons name={st.icon as never} size={11} color={st.txt} />
                  <Text style={[s.badgeTxt, { color: st.txt }]}>{st.label}</Text>
                </View>
              </View>
              <Text style={{ fontSize: 10, color: '#94a3b8', marginTop: 4 }}>{dem.date_demande}</Text>
            </View>
          )
        })}
      </View>

      {/* Mes documents */}
      <View style={[s.card, { margin: 12, marginTop: 0 }]}>
        <Text style={s.cardTitle}>Mes documents</Text>
        {mesDocs.map(doc => {
          const cfg = TYPE_DOC_CONFIG[doc.type]
          const statut = STATUT_DOC[doc.statut]
          return (
            <View key={doc.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' }}>
              <View style={[s.docIcon, { width: 34, height: 34, backgroundColor: cfg.couleur + '18' }]}>
                <Ionicons name={cfg.icon as never} size={16} color={cfg.couleur} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: '#1e293b' }}>{cfg.label} — {doc.periode}</Text>
                <Text style={{ fontSize: 10, color: '#94a3b8' }}>{doc.date_upload}</Text>
              </View>
              <View style={[s.badge, { backgroundColor: statut.bg }]}>
                <Text style={[s.badgeTxt, { color: statut.txt }]}>{statut.label}</Text>
              </View>
              <TouchableOpacity onPress={() => Alert.alert('Téléchargement', `${cfg.label} en cours...`)}>
                <Ionicons name="download-outline" size={18} color="#1d4ed8" />
              </TouchableOpacity>
            </View>
          )
        })}
      </View>

      {/* Modal nouvelle demande */}
      <Modal visible={modalDemande} animationType="slide" presentationStyle="pageSheet">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Nouvelle demande</Text>
            <TouchableOpacity onPress={() => setModalDemande(false)}>
              <Ionicons name="close" size={24} color="#64748b" />
            </TouchableOpacity>
          </View>
          <ScrollView style={{ padding: 16 }}>
            {/* Circuit de validation */}
            <View style={{ backgroundColor: '#eff6ff', borderRadius: 8, padding: 10, marginBottom: 16, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
              <Ionicons name="git-branch-outline" size={14} color="#1d4ed8" />
              <Text style={{ fontSize: 11, color: '#1d4ed8', flex: 1 }}>
                Circuit : {MOI_NOM} → {MOI_RESPONSABLE} (N+1) → Service RH
              </Text>
            </View>

            <Text style={s.fieldLabel}>Type de demande</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {typesDem.map(t => (
                <TouchableOpacity
                  key={t.id}
                  onPress={() => setType(t.id)}
                  style={[s.typeChip, type === t.id && s.typeChipActive]}
                >
                  <Ionicons name={t.icon as never} size={14} color={type === t.id ? '#fff' : '#475569'} />
                  <Text style={[s.typeChipTxt, type === t.id && { color: '#fff' }]}>{t.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={s.fieldLabel}>Description</Text>
            <TextInput
              style={[s.input, { height: 80, textAlignVertical: 'top' }]}
              multiline
              placeholder="Décrivez votre demande..."
              value={description}
              onChangeText={setDescription}
              placeholderTextColor="#94a3b8"
            />

            {(type === 'conge' || type === 'formation') && (
              <>
                <Text style={s.fieldLabel}>Date de début</Text>
                <TextInput
                  style={s.input}
                  placeholder="YYYY-MM-DD"
                  value={dateDebut}
                  onChangeText={setDateDebut}
                  placeholderTextColor="#94a3b8"
                />
                <Text style={s.fieldLabel}>Date de fin</Text>
                <TextInput
                  style={s.input}
                  placeholder="YYYY-MM-DD"
                  value={dateFin}
                  onChangeText={setDateFin}
                  placeholderTextColor="#94a3b8"
                />
              </>
            )}

            <TouchableOpacity style={[s.btnPrimary, envoi && { opacity: 0.6 }]} onPress={soumettre} disabled={envoi}>
              {envoi ? <ActivityIndicator color="#fff" size="small" /> : (
                <>
                  <Ionicons name="send-outline" size={16} color="#fff" />
                  <Text style={{ color: '#fff', fontWeight: '700', fontSize: 15 }}>Soumettre la demande</Text>
                </>
              )}
            </TouchableOpacity>
          </ScrollView>
        </KeyboardAvoidingView>
      </Modal>
    </ScrollView>
  )
}

// ─── Validation RH : onglet dédié pour le Service RH ─────────────────────────

function OngletValidationDemandes() {
  const [demandes, setDemandes] = useState<DemandeRH[]>(DEMANDES_DEMO)
  const [modalCommentaire, setModalCommentaire] = useState(false)
  const [selectedDem, setSelectedDem] = useState<DemandeRH | null>(null)
  const [commentaire, setCommentaire] = useState('')
  const [actionType, setActionType] = useState<'approuve' | 'refuse'>('approuve')

  const enAttente = demandes.filter(d => d.statut === 'en_attente')
  const traitees = demandes.filter(d => d.statut !== 'en_attente')

  const ouvrir = (dem: DemandeRH, action: 'approuve' | 'refuse') => {
    setSelectedDem(dem)
    setActionType(action)
    setCommentaire('')
    setModalCommentaire(true)
  }

  const valider = () => {
    if (!selectedDem) return
    setDemandes(prev => prev.map(d =>
      d.id === selectedDem.id
        ? { ...d, statut: actionType, commentaire_rh: commentaire || (actionType === 'approuve' ? 'Approuvé par le Service RH.' : 'Refusé par le Service RH.') }
        : d
    ))
    setModalCommentaire(false)
    Alert.alert(
      actionType === 'approuve' ? 'Demande approuvée ✓' : 'Demande refusée',
      `La demande de ${selectedDem.employe_nom} a été ${actionType === 'approuve' ? 'approuvée' : 'refusée'}.\nL'employé sera notifié.`
    )
  }

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={{ padding: 12, gap: 12, paddingBottom: 30 }}>
        {/* En attente */}
        {enAttente.length > 0 && (
          <View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#f59e0b' }} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>
                En attente de validation ({enAttente.length})
              </Text>
            </View>
            {enAttente.map(dem => (
              <View key={dem.id} style={[s.card, { marginBottom: 10 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: '#1e293b' }}>
                      {TYPE_DEM_LABELS[dem.type] || dem.type}
                    </Text>
                    <Text style={{ fontSize: 12, color: '#475569', marginTop: 2 }}>{dem.employe_nom}</Text>
                    <Text style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{dem.description}</Text>
                    {(dem.date_debut || dem.date_fin) && (
                      <Text style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                        📅 {dem.date_debut}{dem.date_fin ? ` → ${dem.date_fin}` : ''}
                      </Text>
                    )}
                  </View>
                  <Text style={{ fontSize: 10, color: '#94a3b8' }}>{dem.date_demande}</Text>
                </View>
                {/* Circuit hiérarchique */}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 8, backgroundColor: '#f8fafc', borderRadius: 6, padding: 7 }}>
                  <Ionicons name="checkmark-circle" size={13} color="#16a34a" />
                  <Text style={{ fontSize: 10, color: '#475569', flex: 1 }}>
                    Validé N+1 · En attente Service RH
                  </Text>
                </View>
                {/* Actions */}
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                  <TouchableOpacity
                    style={[s.btnSm, { flex: 1, backgroundColor: '#dcfce7' }]}
                    onPress={() => ouvrir(dem, 'approuve')}
                  >
                    <Ionicons name="checkmark-outline" size={14} color="#16a34a" />
                    <Text style={{ fontSize: 12, color: '#16a34a', fontWeight: '700' }}>Approuver</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.btnSm, { flex: 1, backgroundColor: '#fee2e2' }]}
                    onPress={() => ouvrir(dem, 'refuse')}
                  >
                    <Ionicons name="close-outline" size={14} color="#dc2626" />
                    <Text style={{ fontSize: 12, color: '#dc2626', fontWeight: '700' }}>Refuser</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        )}

        {enAttente.length === 0 && (
          <View style={[s.empty, { marginTop: 20 }]}>
            <Ionicons name="checkmark-done-circle-outline" size={40} color="#16a34a" />
            <Text style={s.emptyTxt}>Aucune demande en attente</Text>
          </View>
        )}

        {/* Traitées */}
        {traitees.length > 0 && (
          <View>
            <Text style={{ fontSize: 12, fontWeight: '700', color: '#64748b', marginBottom: 8, marginTop: 4 }}>
              Traitées récemment
            </Text>
            {traitees.map(dem => {
              const st = STATUT_DEM[dem.statut]
              return (
                <View key={dem.id} style={[s.card, { marginBottom: 8, opacity: 0.8 }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={[s.badge, { backgroundColor: st.bg }]}>
                      <Ionicons name={st.icon as never} size={11} color={st.txt} />
                      <Text style={[s.badgeTxt, { color: st.txt }]}>{st.label}</Text>
                    </View>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: '#1e293b', flex: 1 }}>
                      {TYPE_DEM_LABELS[dem.type]} · {dem.employe_nom}
                    </Text>
                    <Text style={{ fontSize: 10, color: '#94a3b8' }}>{dem.date_demande}</Text>
                  </View>
                  {dem.commentaire_rh && (
                    <Text style={{ fontSize: 11, color: '#475569', marginTop: 6, fontStyle: 'italic' }}>
                      💬 {dem.commentaire_rh}
                    </Text>
                  )}
                </View>
              )
            })}
          </View>
        )}
      </ScrollView>

      {/* Modal commentaire */}
      <Modal visible={modalCommentaire} animationType="slide" presentationStyle="formSheet" transparent>
        <View style={{ flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' }}>
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={{ backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20 }}>
              <Text style={s.modalTitle}>
                {actionType === 'approuve' ? '✓ Approuver la demande' : '✗ Refuser la demande'}
              </Text>
              <Text style={{ fontSize: 12, color: '#64748b', marginTop: 4, marginBottom: 16 }}>
                {selectedDem?.employe_nom} — {TYPE_DEM_LABELS[selectedDem?.type ?? ''] || selectedDem?.type}
              </Text>
              <Text style={s.fieldLabel}>Commentaire (optionnel)</Text>
              <TextInput
                style={[s.input, { height: 70, textAlignVertical: 'top' }]}
                multiline
                placeholder="Motif, instructions, remarques..."
                value={commentaire}
                onChangeText={setCommentaire}
                placeholderTextColor="#94a3b8"
                autoFocus
              />
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                <TouchableOpacity
                  style={[s.btnSm, { flex: 1, backgroundColor: '#f1f5f9', paddingVertical: 12, borderRadius: 10 }]}
                  onPress={() => setModalCommentaire(false)}
                >
                  <Text style={{ fontSize: 14, fontWeight: '600', color: '#64748b' }}>Annuler</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.btnSm, { flex: 2, backgroundColor: actionType === 'approuve' ? '#16a34a' : '#dc2626', paddingVertical: 12, borderRadius: 10 }]}
                  onPress={valider}
                >
                  <Ionicons name={actionType === 'approuve' ? 'checkmark-outline' : 'close-outline'} size={16} color="#fff" />
                  <Text style={{ fontSize: 14, fontWeight: '700', color: '#fff' }}>
                    {actionType === 'approuve' ? 'Confirmer approbation' : 'Confirmer refus'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>
    </View>
  )
}

// ─── Écran principal RH ───────────────────────────────────────────────────────

export default function RHScreen() {
  const [modeVue, setModeVue] = useState<ModeVue>('rh')
  const [onglet, setOnglet] = useState<OngletRH>('demandes')
  const router = useRouter()

  const tabs: { id: OngletRH; label: string; icon: string }[] = [
    { id: 'demandes', label: 'Validation',   icon: 'shield-checkmark-outline' },
    { id: 'kpi',      label: 'Performance',  icon: 'podium-outline' },
    { id: 'documents',label: 'Documents',    icon: 'folder-outline' },
  ]

  return (
    <View style={{ flex: 1, backgroundColor: '#f1f5f9' }}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
          <Ionicons name="arrow-back" size={20} color="#1e40af" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>Module RH</Text>
          <Text style={s.headerSub}>{modeVue === 'employe' ? 'Mon espace employé' : 'Service RH — Administration'}</Text>
        </View>
      </View>

      {/* Switcher Vue */}
      <View style={{ flexDirection: 'row', backgroundColor: '#fff', padding: 8, gap: 8, borderBottomWidth: 1, borderBottomColor: '#e2e8f0' }}>
        <TouchableOpacity
          style={[s.modeBtn, modeVue === 'employe' && s.modeBtnActive]}
          onPress={() => setModeVue('employe')}
        >
          <Ionicons name="person-outline" size={14} color={modeVue === 'employe' ? '#fff' : '#64748b'} />
          <Text style={[s.modeBtnTxt, modeVue === 'employe' && { color: '#fff' }]}>Mon espace</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[s.modeBtn, modeVue === 'rh' && s.modeBtnActive]}
          onPress={() => setModeVue('rh')}
        >
          <Ionicons name="people-outline" size={14} color={modeVue === 'rh' ? '#fff' : '#64748b'} />
          <Text style={[s.modeBtnTxt, modeVue === 'rh' && { color: '#fff' }]}>Service RH</Text>
        </TouchableOpacity>
      </View>

      {/* Vue Employé */}
      {modeVue === 'employe' && <PortailEmploye />}

      {/* Vue Service RH */}
      {modeVue === 'rh' && (
        <>
          {/* Onglets RH */}
          <View style={s.tabBar}>
            {tabs.map(t => (
              <TouchableOpacity
                key={t.id}
                style={[s.tab, onglet === t.id && s.tabActive]}
                onPress={() => setOnglet(t.id)}
              >
                <Ionicons name={t.icon as never} size={16} color={onglet === t.id ? '#1d4ed8' : '#94a3b8'} />
                <Text style={[s.tabLabel, onglet === t.id && s.tabLabelActive]}>{t.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {onglet === 'demandes'  && <OngletValidationDemandes />}
          {onglet === 'kpi'       && <OngletKPI />}
          {onglet === 'documents' && <OngletDocuments />}
        </>
      )}
    </View>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  header: {
    backgroundColor: '#fff',
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    gap: 12,
  },
  backBtn: { padding: 6, borderRadius: 8, backgroundColor: '#eff6ff' },
  headerTitle: { fontSize: 16, fontWeight: '700', color: '#1e293b' },
  headerSub: { fontSize: 11, color: '#64748b', marginTop: 1 },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    paddingHorizontal: 4,
  },
  tab: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 12, gap: 5, borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: '#1d4ed8' },
  tabLabel: { fontSize: 12, color: '#94a3b8', fontWeight: '600' },
  tabLabelActive: { color: '#1d4ed8' },
  card: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05, shadowRadius: 3, elevation: 2,
  },
  cardTitle: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 20,
  },
  badgeTxt: { fontSize: 11, fontWeight: '600' },
  avatar: {
    width: 38, height: 38, borderRadius: 19,
    alignItems: 'center', justifyContent: 'center',
  },
  rang: {
    width: 32, height: 32, borderRadius: 8,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#f8fafc',
  },
  docIcon: {
    width: 42, height: 42, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center',
  },
  searchBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#fff', margin: 12, marginBottom: 8, borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 10,
    borderWidth: 1, borderColor: '#e2e8f0',
  },
  searchInput: { flex: 1, fontSize: 13, color: '#1e293b' },
  chip: {
    paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20,
    backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0',
  },
  chipActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  chipText: { fontSize: 12, color: '#64748b', fontWeight: '600' },
  chipTextActive: { color: '#fff' },
  btnSm: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 5, paddingVertical: 7, borderRadius: 8,
  },
  fab: {
    position: 'absolute', bottom: 24, right: 24,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: '#1d4ed8', alignItems: 'center', justifyContent: 'center',
    shadowColor: '#1d4ed8', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4, shadowRadius: 8, elevation: 8,
  },
  empty: { alignItems: 'center', paddingVertical: 40, gap: 10 },
  emptyTxt: { fontSize: 14, color: '#94a3b8' },
  infoBanner: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    backgroundColor: '#eff6ff', margin: 12, marginBottom: 4,
    borderRadius: 8, padding: 10, borderLeftWidth: 3, borderLeftColor: '#1d4ed8',
  },
  infoBannerTxt: { flex: 1, fontSize: 11, color: '#1d4ed8', lineHeight: 16 },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: 16, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  modalTitle: { fontSize: 16, fontWeight: '700', color: '#1e293b' },
  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#475569', marginBottom: 6, marginTop: 4 },
  input: {
    backgroundColor: '#f8fafc', borderRadius: 8, padding: 12,
    fontSize: 13, color: '#1e293b', borderWidth: 1, borderColor: '#e2e8f0',
    marginBottom: 12,
  },
  typeChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20,
    backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0',
  },
  typeChipActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  typeChipTxt: { fontSize: 12, color: '#475569', fontWeight: '600' },
  btnPrimary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 8, backgroundColor: '#1d4ed8', borderRadius: 10,
    paddingVertical: 14, marginTop: 8, marginBottom: 20,
  },
  modeBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 8, borderRadius: 8,
    backgroundColor: '#f1f5f9',
  },
  modeBtnActive: { backgroundColor: '#1d4ed8' },
  modeBtnTxt: { fontSize: 13, fontWeight: '600', color: '#64748b' },
})
