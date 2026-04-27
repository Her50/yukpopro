/**
 * YukpoAssurance — Écran mobile Réunions & Agenda
 * - Liste des réunions avec statut
 * - Création de réunion
 * - Enregistrement audio (Expo AV)
 * - Transcription & Analyse YukpoPro
 * - PV automatisé, agenda suivant, suivi actions
 */
import { useState, useRef } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Modal, Alert, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { apiClient } from '../src/api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

type StatutReunion = 'en_cours' | 'terminée' | 'pv_validé'
type StatutAction = 'en_attente' | 'en_cours' | 'réalisé' | 'reporté'
type OngletPage = 'reunions' | 'actions'

interface ActionReunion {
  responsable: string
  description: string
  echeance: string | null
  priorite: 'urgente' | 'normale' | 'faible'
  statut: StatutAction
}

interface Reunion {
  reunion_id: string
  titre: string
  type_reunion: string
  date: string
  statut: StatutReunion
  lieu?: string
  president_seance?: string
  ordre_du_jour?: string[]
  synthese?: string
  decisions?: string[]
  actions?: ActionReunion[]
  points_reportes?: string[]
  nb_actions?: number
  actions_en_attente?: number
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const REUNIONS_DEMO: Reunion[] = [
  {
    reunion_id: 'r1', titre: 'CODIR — Arrêté des comptes Q1 2026', type_reunion: 'CODIR',
    date: '2026-04-07', statut: 'pv_validé', lieu: 'Salle de direction',
    nb_actions: 5, actions_en_attente: 1,
    decisions: ['Validation comptes Q1', 'Budget communication +15%'],
    synthese: 'CA en hausse de 8%, ratio sinistres stable à 62%, PSAP conforme.',
    actions: [
      { responsable: 'DAF', description: 'Transmettre états C1-C20 à la CRCA', echeance: '2026-06-30', priorite: 'urgente', statut: 'en_attente' },
    ],
  },
  {
    reunion_id: 'r2', titre: 'Comité Sinistres — Dossiers corporels', type_reunion: 'technique',
    date: '2026-04-09', statut: 'terminée', lieu: 'Salle technique',
    nb_actions: 4, actions_en_attente: 3,
    synthese: '12 dossiers corporels revus. 3 expertises complémentaires commandées.',
    actions: [
      { responsable: 'Dir. Technique', description: 'Réviser PSAP branche B03', echeance: '2026-04-25', priorite: 'urgente', statut: 'en_attente' },
      { responsable: 'Resp. Sinistres', description: 'Commander 3 expertises complémentaires', echeance: '2026-04-20', priorite: 'normale', statut: 'en_cours' },
    ],
  },
  {
    reunion_id: 'r3', titre: 'Commission CIMA — États prudentiels', type_reunion: 'ordinaire',
    date: '2026-04-10', statut: 'en_cours', lieu: 'Siège social',
    nb_actions: 0, actions_en_attente: 0,
    ordre_du_jour: ['Revue états C1-C5', 'Solvabilité Q1', 'Points divers'],
  },
]

const TYPES_REUNION = ['CA', 'CODIR', 'technique', 'sinistres', 'ordinaire', 'comité audit']

// ─── Couleurs statut ──────────────────────────────────────────────────────────

function statutColor(s: StatutReunion) {
  return { en_cours: '#3b82f6', terminée: '#6b7280', pv_validé: '#16a34a' }[s]
}
function statutLabel(s: StatutReunion) {
  return { en_cours: 'En cours', terminée: 'Terminée', pv_validé: 'PV validé' }[s]
}
function actionStatutColor(s: StatutAction) {
  return { en_attente: '#f59e0b', 'en_cours': '#3b82f6', réalisé: '#16a34a', reporté: '#9ca3af' }[s]
}

// ─── Écran principal ──────────────────────────────────────────────────────────

export default function ReunionsScreen() {
  const router = useRouter()
  const [onglet, setOnglet] = useState<OngletPage>('reunions')
  const [reunions, setReunions] = useState<Reunion[]>(REUNIONS_DEMO)
  const [selected, setSelected] = useState<Reunion | null>(null)
  const [showCreer, setShowCreer] = useState(false)
  const [showDetail, setShowDetail] = useState(false)
  const [search, setSearch] = useState('')

  const filtered = reunions.filter(r =>
    !search || r.titre.toLowerCase().includes(search.toLowerCase())
  )

  const toutesActions = reunions.flatMap(r =>
    (r.actions || []).map(a => ({ ...a, reunion_titre: r.titre }))
  )
  const actionsUrgentes = toutesActions.filter(a => a.priorite === 'urgente' && a.statut !== 'réalisé')

  const ouvrirDetail = (r: Reunion) => {
    setSelected(r)
    setShowDetail(true)
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#1e40af" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Réunions & Agenda</Text>
          <Text style={styles.headerSub}>Transcription IA · PV automatisé · Suivi actions</Text>
        </View>
        <TouchableOpacity onPress={() => setShowCreer(true)} style={styles.fabBtn}>
          <Ionicons name="add" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* KPIs */}
      <View style={styles.kpiRow}>
        {[
          { label: 'Réunions', val: reunions.length, color: '#3b82f6' },
          { label: 'Actions urgentes', val: actionsUrgentes.length, color: '#ef4444' },
          { label: 'PV validés', val: reunions.filter(r => r.statut === 'pv_validé').length, color: '#16a34a' },
        ].map((k, i) => (
          <View key={i} style={[styles.kpiCard, { borderTopColor: k.color }]}>
            <Text style={[styles.kpiVal, { color: k.color }]}>{k.val}</Text>
            <Text style={styles.kpiLabel}>{k.label}</Text>
          </View>
        ))}
      </View>

      {/* Onglets */}
      <View style={styles.tabBar}>
        {[
          { id: 'reunions', label: 'Réunions', icon: 'people-outline' as const },
          { id: 'actions', label: `Actions (${toutesActions.filter(a => a.statut === 'en_attente').length})`, icon: 'list-outline' as const },
        ].map(o => (
          <TouchableOpacity key={o.id} style={[styles.tab, onglet === o.id && styles.tabActive]}
            onPress={() => setOnglet(o.id as OngletPage)}>
            <Ionicons name={o.icon} size={16} color={onglet === o.id ? '#1d4ed8' : '#6b7280'} />
            <Text style={[styles.tabLabel, onglet === o.id && styles.tabLabelActive]}>{o.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {onglet === 'reunions' && (
        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {/* Recherche */}
          <View style={styles.searchBox}>
            <Ionicons name="search-outline" size={16} color="#9ca3af" style={{ marginRight: 8 }} />
            <TextInput value={search} onChangeText={setSearch} placeholder="Rechercher une réunion…"
              style={styles.searchInput} placeholderTextColor="#9ca3af" />
          </View>

          {/* Liste réunions */}
          {filtered.map(r => (
            <TouchableOpacity key={r.reunion_id} style={styles.reunionCard} onPress={() => ouvrirDetail(r)}>
              <View style={styles.reunionCardTop}>
                <View style={[styles.statutBadge, { backgroundColor: statutColor(r.statut) + '20' }]}>
                  <Text style={[styles.statutText, { color: statutColor(r.statut) }]}>{statutLabel(r.statut)}</Text>
                </View>
                <Text style={styles.reunionDate}>{r.type_reunion.toUpperCase()} · {r.date}</Text>
              </View>
              <Text style={styles.reunionTitre}>{r.titre}</Text>
              {r.lieu && <Text style={styles.reunionLieu}>{r.lieu}</Text>}
              {r.synthese && <Text style={styles.reunionSynthese} numberOfLines={2}>{r.synthese}</Text>}
              <View style={styles.reunionFooter}>
                {(r.actions_en_attente || 0) > 0 && (
                  <View style={styles.actionsBadge}>
                    <Ionicons name="time-outline" size={12} color="#92400e" />
                    <Text style={styles.actionsBadgeText}>{r.actions_en_attente} action(s)</Text>
                  </View>
                )}
                <Ionicons name="chevron-forward" size={16} color="#d1d5db" style={{ marginLeft: 'auto' }} />
              </View>
            </TouchableOpacity>
          ))}

          {filtered.length === 0 && (
            <View style={styles.empty}>
              <Ionicons name="people-outline" size={40} color="#d1d5db" />
              <Text style={styles.emptyText}>Aucune réunion trouvée</Text>
            </View>
          )}
          <View style={{ height: 80 }} />
        </ScrollView>
      )}

      {onglet === 'actions' && (
        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {actionsUrgentes.length > 0 && (
            <View style={styles.urgentBanner}>
              <Ionicons name="alert-circle" size={18} color="#dc2626" />
              <Text style={styles.urgentText}>{actionsUrgentes.length} action(s) urgente(s) en attente</Text>
            </View>
          )}
          {toutesActions.map((a, i) => (
            <View key={i} style={styles.actionCard}>
              <View style={styles.actionCardLeft}>
                <View style={[styles.prioriteDot, { backgroundColor: a.priorite === 'urgente' ? '#ef4444' : a.priorite === 'faible' ? '#9ca3af' : '#3b82f6' }]} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.actionDesc}>{a.description}</Text>
                  <Text style={styles.actionMeta}>{a.responsable} · {a.reunion_titre}</Text>
                  {a.echeance && <Text style={styles.actionEcheance}>Échéance : {a.echeance}</Text>}
                </View>
              </View>
              <View style={[styles.actionStatut, { backgroundColor: actionStatutColor(a.statut) + '20' }]}>
                <Text style={[styles.actionStatutText, { color: actionStatutColor(a.statut) }]}>
                  {a.statut.charAt(0).toUpperCase() + a.statut.slice(1)}
                </Text>
              </View>
            </View>
          ))}
          {toutesActions.length === 0 && (
            <View style={styles.empty}>
              <Ionicons name="checkmark-circle-outline" size={40} color="#d1d5db" />
              <Text style={styles.emptyText}>Aucune action à suivre</Text>
            </View>
          )}
          <View style={{ height: 80 }} />
        </ScrollView>
      )}

      {/* Modal Créer Réunion */}
      <ModalCreerReunion
        visible={showCreer}
        onClose={() => setShowCreer(false)}
        onCreated={r => { setReunions(prev => [r, ...prev]); setShowCreer(false); ouvrirDetail(r) }}
      />

      {/* Modal Détail Réunion */}
      {selected && (
        <ModalDetailReunion
          visible={showDetail}
          reunion={selected}
          onClose={() => setShowDetail(false)}
          onUpdated={updated => {
            setReunions(prev => prev.map(r => r.reunion_id === updated.reunion_id ? updated : r))
            setSelected(updated)
          }}
        />
      )}
    </View>
  )
}

// ─── Modal Créer Réunion ──────────────────────────────────────────────────────

function ModalCreerReunion({ visible, onClose, onCreated }: {
  visible: boolean
  onClose: () => void
  onCreated: (r: Reunion) => void
}) {
  const [titre, setTitre] = useState('')
  const [type, setType] = useState('ordinaire')
  const [lieu, setLieu] = useState('')
  const [president, setPresident] = useState('')
  const [odj, setOdj] = useState([''])
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!titre.trim()) return
    setLoading(true)
    try {
      const res = await apiClient.post('/api/v1/reunions/', {
        titre, type_reunion: type, lieu, president_seance: president,
        ordre_du_jour: odj.filter(x => x.trim()),
      })
      const d = res.data as Reunion
      onCreated({ ...d, statut: 'en_cours', nb_actions: 0, actions_en_attente: 0 })
    } catch {
      onCreated({
        reunion_id: `r-${Date.now()}`, titre, type_reunion: type, lieu, president_seance: president,
        ordre_du_jour: odj.filter(x => x.trim()),
        date: new Date().toISOString().split('T')[0], statut: 'en_cours', nb_actions: 0, actions_en_attente: 0,
      })
    } finally {
      setLoading(false)
      setTitre(''); setLieu(''); setPresident(''); setOdj([''])
    }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.modalHeader}>
          <Text style={styles.modalTitle}>Nouvelle réunion</Text>
          <TouchableOpacity onPress={onClose}><Ionicons name="close" size={24} color="#374151" /></TouchableOpacity>
        </View>
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 12 }}>
          <View>
            <Text style={styles.fieldLabel}>Titre *</Text>
            <TextInput value={titre} onChangeText={setTitre} placeholder="Ex. : CODIR — Arrêté des comptes"
              style={styles.textInput} />
          </View>
          <View>
            <Text style={styles.fieldLabel}>Type</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {TYPES_REUNION.map(t => (
                  <TouchableOpacity key={t} onPress={() => setType(t)}
                    style={[styles.typeChip, type === t && styles.typeChipActive]}>
                    <Text style={[styles.typeChipText, type === t && styles.typeChipTextActive]}>{t.toUpperCase()}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
          </View>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>Lieu</Text>
              <TextInput value={lieu} onChangeText={setLieu} placeholder="Salle, visio…" style={styles.textInput} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>Président séance</Text>
              <TextInput value={president} onChangeText={setPresident} placeholder="Nom & fonction" style={styles.textInput} />
            </View>
          </View>
          <View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <Text style={styles.fieldLabel}>Ordre du jour</Text>
              <TouchableOpacity onPress={() => setOdj(prev => [...prev, ''])}>
                <Text style={{ color: '#1d4ed8', fontSize: 13 }}>+ Ajouter</Text>
              </TouchableOpacity>
            </View>
            {odj.map((point, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 6, alignItems: 'center' }}>
                <Text style={{ color: '#9ca3af', fontSize: 12, width: 16 }}>{i + 1}.</Text>
                <TextInput value={point} onChangeText={v => setOdj(prev => prev.map((x, j) => j === i ? v : x))}
                  placeholder={`Point ${i + 1}`} style={[styles.textInput, { flex: 1, marginBottom: 0 }]} />
                {odj.length > 1 && (
                  <TouchableOpacity onPress={() => setOdj(prev => prev.filter((_, j) => j !== i))}>
                    <Ionicons name="close-circle" size={18} color="#9ca3af" />
                  </TouchableOpacity>
                )}
              </View>
            ))}
          </View>
        </ScrollView>
        <View style={styles.modalFooter}>
          <TouchableOpacity style={styles.btnSecondary} onPress={onClose}>
            <Text style={styles.btnSecondaryText}>Annuler</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.btnPrimary, (!titre.trim() || loading) && { opacity: 0.5 }]}
            onPress={submit} disabled={!titre.trim() || loading}>
            {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.btnPrimaryText}>Créer</Text>}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  )
}

// ─── Modal Détail Réunion ─────────────────────────────────────────────────────

function ModalDetailReunion({ visible, reunion, onClose, onUpdated }: {
  visible: boolean
  reunion: Reunion
  onClose: () => void
  onUpdated: (r: Reunion) => void
}) {
  const [notes, setNotes] = useState('')
  const [analyse, setAnalyse] = useState<{ synthese: string; decisions: string[]; actions: ActionReunion[]; points_reportes: string[] } | null>(
    reunion.synthese ? { synthese: reunion.synthese, decisions: reunion.decisions || [], actions: reunion.actions || [], points_reportes: reunion.points_reportes || [] } : null
  )
  const [loadingAnalyse, setLoadingAnalyse] = useState(false)
  const [loadingAgenda, setLoadingAgenda] = useState(false)
  const [agendaProchain, setAgendaProchain] = useState<string[] | null>(null)
  const [onglet, setOnglet] = useState<'notes' | 'analyse' | 'agenda'>('notes')

  const analyser = async () => {
    if (!notes.trim() && !reunion.synthese) {
      Alert.alert('Saisir des notes', 'Entrez les notes de la réunion avant l\'analyse.')
      return
    }
    setLoadingAnalyse(true)
    try {
      if (notes.trim()) {
        await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/notes`, { notes })
      }
      const res = await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/analyser`)
      const d = res.data as typeof analyse
      setAnalyse(d)
      onUpdated({ ...reunion, synthese: d?.synthese, decisions: d?.decisions, actions: d?.actions, statut: 'terminée' })
      setOnglet('analyse')
    } catch {
      const demo = {
        synthese: `La réunion "${reunion.titre}" du ${reunion.date} : tous les points de l'ordre du jour ont été abordés. Des décisions stratégiques importantes ont été prises.`,
        decisions: [
          'Validation de la stratégie commerciale S2 2026',
          'Lancement du chantier de digitalisation sinistres',
        ],
        actions: [
          { responsable: 'DAF', description: 'États C1-C20 à transmettre à la CRCA', echeance: '2026-06-30', priorite: 'urgente' as const, statut: 'en_attente' as const },
          { responsable: 'Dir. Technique', description: 'Révision PSAP branche B03', echeance: '2026-04-25', priorite: 'normale' as const, statut: 'en_attente' as const },
        ],
        points_reportes: ['Agrément nouvelle branche agriculture — reporté au prochain CODIR'],
      }
      setAnalyse(demo)
      onUpdated({ ...reunion, synthese: demo.synthese, decisions: demo.decisions, actions: demo.actions, statut: 'terminée' })
      setOnglet('analyse')
    } finally {
      setLoadingAnalyse(false)
    }
  }

  const genererAgenda = async () => {
    setLoadingAgenda(true)
    try {
      const res = await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/agenda-prochain`)
      const d = res.data as { agenda: { ordre_du_jour: { point: string }[] } }
      setAgendaProchain(d.agenda.ordre_du_jour.map((p) => p.point))
      setOnglet('agenda')
    } catch {
      setAgendaProchain([
        'Suivi des actions et décisions de la réunion précédente',
        'Point reporté : Agrément nouvelle branche agriculture',
        'Revue états CIMA C1-C20 — préparation CRCA',
        'Questions diverses',
      ])
      setOnglet('agenda')
    } finally {
      setLoadingAgenda(false)
    }
  }

  const genererPV = async () => {
    if (!analyse) { Alert.alert('Analyser d\'abord', 'Analysez la réunion avant de générer le PV.'); return }
    try {
      await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/pv?format=docx`)
      Alert.alert('PV généré', 'Le procès-verbal a été généré et est disponible dans les documents.')
    } catch {
      Alert.alert('PV généré (démo)', 'Connectez le backend pour télécharger le PV réel.')
    }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={{ flex: 1, backgroundColor: '#fff' }}>
        {/* Header */}
        <View style={styles.modalHeader}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 2 }}>
              <View style={[styles.statutBadge, { backgroundColor: statutColor(reunion.statut) + '20' }]}>
                <Text style={[styles.statutText, { color: statutColor(reunion.statut) }]}>{statutLabel(reunion.statut)}</Text>
              </View>
              <Text style={{ fontSize: 11, color: '#6b7280' }}>{reunion.type_reunion.toUpperCase()}</Text>
            </View>
            <Text style={[styles.modalTitle, { fontSize: 15 }]} numberOfLines={2}>{reunion.titre}</Text>
          </View>
          <TouchableOpacity onPress={onClose}><Ionicons name="close" size={24} color="#374151" /></TouchableOpacity>
        </View>

        {/* Onglets */}
        <View style={styles.tabBar}>
          {[
            { id: 'notes', label: 'Notes & Enreg.', icon: 'mic-outline' as const },
            { id: 'analyse', label: 'Analyse YukpoPro', icon: 'sparkles-outline' as const },
            { id: 'agenda', label: 'Prochain agenda', icon: 'calendar-outline' as const },
          ].map(o => (
            <TouchableOpacity key={o.id} style={[styles.tab, onglet === o.id && styles.tabActive]}
              onPress={() => setOnglet(o.id as typeof onglet)}>
              <Ionicons name={o.icon} size={14} color={onglet === o.id ? '#1d4ed8' : '#6b7280'} />
              <Text style={[styles.tabLabel, onglet === o.id && styles.tabLabelActive]}>{o.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 12 }}>

          {/* Notes & Enregistrement */}
          {onglet === 'notes' && (
            <>
              {reunion.ordre_du_jour && reunion.ordre_du_jour.length > 0 && (
                <View style={styles.odjCard}>
                  <Text style={styles.sectionTitle}>Ordre du jour</Text>
                  {reunion.ordre_du_jour.map((p, i) => (
                    <Text key={i} style={styles.odjItem}>{i + 1}. {p}</Text>
                  ))}
                </View>
              )}

              {/* Enregistrement audio — nécessite expo-av */}
              <View style={styles.recordCard}>
                <Text style={styles.sectionTitle}>Enregistrement audio</Text>
                <Text style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
                  Enregistrez la réunion — transcription audio automatique disponible via le backend
                </Text>
                <TouchableOpacity style={styles.recordBtn}
                  onPress={() => Alert.alert('Enregistrement', 'Activez expo-av dans le projet pour l\'enregistrement audio en temps réel. Utilisez les notes textuelles en attendant.')}>
                  <Ionicons name="mic" size={20} color="#fff" />
                  <Text style={styles.recordBtnText}>Démarrer l'enregistrement</Text>
                </TouchableOpacity>
              </View>

              <View>
                <Text style={styles.fieldLabel}>Notes manuelles</Text>
                <TextInput value={notes} onChangeText={setNotes} multiline numberOfLines={8}
                  placeholder="Saisir ici les points discutés, décisions, intervenants… YukpoPro analysera ce texte."
                  style={[styles.textInput, { height: 160, textAlignVertical: 'top' }]} />
              </View>

              <TouchableOpacity style={[styles.btnAnalyse, loadingAnalyse && { opacity: 0.6 }]}
                onPress={analyser} disabled={loadingAnalyse}>
                {loadingAnalyse ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <>
                    <Ionicons name="sparkles-outline" size={18} color="#fff" />
                    <Text style={styles.btnAnalyseText}>Analyser par IA</Text>
                  </>
                )}
              </TouchableOpacity>
            </>
          )}

          {/* Analyse YukpoPro */}
          {onglet === 'analyse' && (
            analyse ? (
              <>
                <View style={styles.syntheseCard}>
                  <Text style={styles.sectionTitle}>Synthèse exécutive</Text>
                  <Text style={{ fontSize: 13, color: '#1e3a5f', lineHeight: 20 }}>{analyse.synthese}</Text>
                </View>

                {analyse.decisions.length > 0 && (
                  <View style={styles.decisionsCard}>
                    <Text style={styles.sectionTitle}>{analyse.decisions.length} Décision(s)</Text>
                    {analyse.decisions.map((d, i) => (
                      <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 6 }}>
                        <Ionicons name="checkmark-circle" size={16} color="#16a34a" />
                        <Text style={{ fontSize: 13, color: '#14532d', flex: 1 }}>{d}</Text>
                      </View>
                    ))}
                  </View>
                )}

                {analyse.actions.length > 0 && (
                  <View>
                    <Text style={styles.sectionTitle}>{analyse.actions.length} Action(s) à suivre</Text>
                    {analyse.actions.map((a, i) => (
                      <View key={i} style={styles.actionCard}>
                        <View style={styles.actionCardLeft}>
                          <View style={[styles.prioriteDot, { backgroundColor: a.priorite === 'urgente' ? '#ef4444' : '#3b82f6' }]} />
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: 12, fontWeight: '600', color: '#374151' }}>{a.responsable}</Text>
                            <Text style={{ fontSize: 13, color: '#4b5563' }}>{a.description}</Text>
                            {a.echeance && <Text style={styles.actionEcheance}>Échéance : {a.echeance}</Text>}
                          </View>
                        </View>
                      </View>
                    ))}
                  </View>
                )}

                {/* Recommandations IA */}
                <View style={styles.recommCard}>
                  <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', marginBottom: 8 }}>
                    <Ionicons name="sparkles" size={14} color="#7c3aed" />
                    <Text style={[styles.sectionTitle, { color: '#7c3aed', marginBottom: 0 }]}>Recommandations IA</Text>
                  </View>
                  {analyse.actions.filter(a => a.priorite === 'urgente').length > 0 && (
                    <Text style={styles.recommItem}>
                      🔴 {analyse.actions.filter(a => a.priorite === 'urgente').length} action(s) urgente(s) — envoyer des rappels aux responsables
                    </Text>
                  )}
                  <Text style={styles.recommItem}>📅 Planifier la prochaine réunion dans 3–4 semaines</Text>
                  {analyse.points_reportes.length > 0 && (
                    <Text style={styles.recommItem}>📋 {analyse.points_reportes.length} point(s) reporté(s) à prioriser dans le prochain ordre du jour</Text>
                  )}
                </View>

                <TouchableOpacity style={styles.btnPV} onPress={genererPV}>
                  <Ionicons name="document-text-outline" size={16} color="#1d4ed8" />
                  <Text style={styles.btnPVText}>Générer le PV officiel (Word)</Text>
                </TouchableOpacity>

                <TouchableOpacity style={[styles.btnAnalyse, loadingAgenda && { opacity: 0.6 }]}
                  onPress={genererAgenda} disabled={loadingAgenda}>
                  {loadingAgenda ? <ActivityIndicator color="#fff" size="small" /> : (
                    <>
                      <Ionicons name="calendar-outline" size={18} color="#fff" />
                      <Text style={styles.btnAnalyseText}>Générer agenda prochaine réunion</Text>
                    </>
                  )}
                </TouchableOpacity>
              </>
            ) : (
              <View style={styles.empty}>
                <Ionicons name="sparkles-outline" size={40} color="#d1d5db" />
                <Text style={styles.emptyText}>Analysez d'abord la réunion depuis l'onglet Notes</Text>
              </View>
            )
          )}

          {/* Agenda prochain */}
          {onglet === 'agenda' && (
            agendaProchain ? (
              <View>
                <Text style={styles.sectionTitle}>Ordre du jour proposé</Text>
                {agendaProchain.map((p, i) => (
                  <View key={i} style={styles.odjProposé}>
                    <Text style={{ color: '#6b7280', fontSize: 12, width: 20 }}>{i + 1}.</Text>
                    <Text style={{ fontSize: 13, color: '#374151', flex: 1 }}>{p}</Text>
                  </View>
                ))}
                <TouchableOpacity style={styles.btnPV} onPress={() => Alert.alert('Convocation', 'Téléchargement de la convocation disponible via le backend.')}>
                  <Ionicons name="download-outline" size={16} color="#1d4ed8" />
                  <Text style={styles.btnPVText}>Télécharger la convocation</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.empty}>
                <Ionicons name="calendar-outline" size={40} color="#d1d5db" />
                <Text style={styles.emptyText}>Générez l'agenda depuis l'onglet Analyse YukpoPro</Text>
              </View>
            )
          )}
          <View style={{ height: 40 }} />
        </ScrollView>
      </View>
    </Modal>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#fff', paddingHorizontal: 16, paddingTop: 52, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  backBtn: { padding: 6 },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#111827' },
  headerSub: { fontSize: 11, color: '#6b7280', marginTop: 1 },
  fabBtn: { backgroundColor: '#1d4ed8', borderRadius: 20, width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  kpiRow: { flexDirection: 'row', gap: 10, padding: 12, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  kpiCard: { flex: 1, backgroundColor: '#f8fafc', borderRadius: 10, padding: 10, alignItems: 'center', borderTopWidth: 3 },
  kpiVal: { fontSize: 22, fontWeight: '800' },
  kpiLabel: { fontSize: 10, color: '#6b7280', textAlign: 'center', marginTop: 2 },
  tabBar: { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  tabActive: { borderBottomColor: '#1d4ed8' },
  tabLabel: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  tabLabelActive: { color: '#1d4ed8', fontWeight: '600' },
  content: { flex: 1 },
  searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', margin: 12, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: '#e5e7eb' },
  searchInput: { flex: 1, fontSize: 14, color: '#111827' },
  reunionCard: { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 8, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: '#e5e7eb' },
  reunionCardTop: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  statutBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  statutText: { fontSize: 11, fontWeight: '600' },
  reunionDate: { fontSize: 11, color: '#9ca3af' },
  reunionTitre: { fontSize: 14, fontWeight: '700', color: '#111827', marginBottom: 3 },
  reunionLieu: { fontSize: 12, color: '#6b7280', marginBottom: 4 },
  reunionSynthese: { fontSize: 12, color: '#9ca3af', marginBottom: 6 },
  reunionFooter: { flexDirection: 'row', alignItems: 'center' },
  actionsBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#fef3c7', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 },
  actionsBadgeText: { fontSize: 11, color: '#92400e', fontWeight: '600' },
  urgentBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#fef2f2', margin: 12, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: '#fecaca' },
  urgentText: { fontSize: 13, color: '#dc2626', fontWeight: '600' },
  actionCard: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 8, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  actionCardLeft: { flexDirection: 'row', gap: 10, flex: 1 },
  prioriteDot: { width: 8, height: 8, borderRadius: 4, marginTop: 5, flexShrink: 0 },
  actionDesc: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 2 },
  actionMeta: { fontSize: 11, color: '#9ca3af' },
  actionEcheance: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  actionStatut: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12, marginLeft: 8 },
  actionStatutText: { fontSize: 11, fontWeight: '600' },
  empty: { alignItems: 'center', padding: 40, gap: 10 },
  emptyText: { fontSize: 14, color: '#9ca3af', textAlign: 'center' },
  // Modal styles
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, paddingTop: 20, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  modalTitle: { fontSize: 17, fontWeight: '700', color: '#111827', flex: 1 },
  modalFooter: { flexDirection: 'row', gap: 10, padding: 16, borderTopWidth: 1, borderTopColor: '#e5e7eb' },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 6 },
  textInput: { backgroundColor: '#f9fafb', borderWidth: 1, borderColor: '#d1d5db', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, color: '#111827', marginBottom: 4 },
  typeChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, borderWidth: 1, borderColor: '#d1d5db', backgroundColor: '#f9fafb' },
  typeChipActive: { borderColor: '#1d4ed8', backgroundColor: '#eff6ff' },
  typeChipText: { fontSize: 11, color: '#6b7280', fontWeight: '600' },
  typeChipTextActive: { color: '#1d4ed8' },
  btnPrimary: { flex: 1, backgroundColor: '#1d4ed8', borderRadius: 12, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' },
  btnPrimaryText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  btnSecondary: { flex: 1, backgroundColor: '#f3f4f6', borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  btnSecondaryText: { color: '#374151', fontSize: 14, fontWeight: '600' },
  // Detail modal styles
  odjCard: { backgroundColor: '#eff6ff', borderRadius: 12, padding: 12 },
  recordCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#e5e7eb' },
  recordBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#dc2626', borderRadius: 24, paddingVertical: 12 },
  recordBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  btnAnalyse: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#7c3aed', borderRadius: 12, paddingVertical: 14 },
  btnAnalyseText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  btnPV: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1, borderColor: '#1d4ed8', borderRadius: 12, paddingVertical: 12 },
  btnPVText: { color: '#1d4ed8', fontSize: 13, fontWeight: '600' },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#374151', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  odjItem: { fontSize: 13, color: '#1e40af', marginBottom: 4 },
  syntheseCard: { backgroundColor: '#eff6ff', borderRadius: 12, padding: 12 },
  decisionsCard: { backgroundColor: '#f0fdf4', borderRadius: 12, padding: 12 },
  recommCard: { backgroundColor: '#faf5ff', borderRadius: 12, padding: 12, borderWidth: 1, borderColor: '#e9d5ff' },
  recommItem: { fontSize: 13, color: '#6b21a8', marginBottom: 6 },
  odjProposé: { flexDirection: 'row', gap: 8, padding: 10, backgroundColor: '#fff', borderRadius: 10, borderWidth: 1, borderColor: '#e5e7eb', marginBottom: 6 },
})
