/**
 * ReunionPage — Gestion complète des réunions IA
 * - Création de réunion avec ordre du jour
 * - Enregistrement audio en temps réel (MediaRecorder)
 * - Transcription automatique Whisper via backend
 * - Analyse YukpoPro : synthèse, décisions, recommandations, actions
 * - Génération PV officiel (Word/PDF)
 * - Proposition agenda réunion suivante
 * - Suivi des actions (tableau de bord)
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import {
  MicrophoneIcon, StopIcon, DocumentTextIcon, SparklesIcon,
  CheckCircleIcon, XMarkIcon, ClockIcon, ExclamationTriangleIcon,
  PlusIcon, ArrowDownTrayIcon, PlayIcon, CalendarDaysIcon,
  UserGroupIcon, ChartBarIcon, MagnifyingGlassIcon, PencilIcon,
  ChevronRightIcon, ArrowPathIcon, BellAlertIcon, ListBulletIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { apiClient } from '../api/client'
import { EmptyState } from '../components/EmptyState'

// ─── Types ────────────────────────────────────────────────────────────────────

type StatutReunion = 'en_cours' | 'terminée' | 'pv_validé'
type StatutAction = 'en_attente' | 'en_cours' | 'réalisé' | 'reporté'
type OngletPage = 'reunions' | 'actions' | 'calendrier'

interface Participant {
  nom: string
  poste: string
  present: boolean
}

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
  participants?: Participant[]
  ordre_du_jour?: string[]
  synthese?: string
  decisions?: string[]
  actions?: ActionReunion[]
  points_reportes?: string[]
  nb_actions?: number
  actions_en_attente?: number
}

interface AnalyseResult {
  synthese: string
  decisions: string[]
  actions: ActionReunion[]
  points_reportes: string[]
  observations?: string
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const REUNIONS_DEMO: Reunion[] = [
  {
    reunion_id: 'r1', titre: 'CODIR — Arrêté des comptes Q1 2026', type_reunion: 'CODIR',
    date: '2026-04-07', statut: 'pv_validé', lieu: 'Salle de direction',
    president_seance: 'DG — M. KOUASSI', nb_actions: 5, actions_en_attente: 1,
    decisions: ['Validation comptes Q1', 'Budget communication augmenté de 15%'],
    synthese: 'Revue trimestrielle : CA en hausse de 8%, ratio sinistres stable à 62%, PSAP conforme.',
  },
  {
    reunion_id: 'r2', titre: 'Comité Sinistres — Dossiers corporels en cours', type_reunion: 'technique',
    date: '2026-04-09', statut: 'terminée', lieu: 'Salle technique',
    president_seance: 'Dir. Technique — Mme TRAORÉ', nb_actions: 4, actions_en_attente: 3,
    synthese: '12 dossiers corporels revus. 3 expertises complémentaires commandées.',
  },
  {
    reunion_id: 'r3', titre: 'Commission CIMA — Préparation états prudentiels', type_reunion: 'ordinaire',
    date: '2026-04-10', statut: 'en_cours', lieu: 'Siège social', nb_actions: 0, actions_en_attente: 0,
  },
]

const TYPES_REUNION = ['CA', 'CODIR', 'technique', 'sinistres', 'ordinaire', 'comité audit', 'comité risques']

// ─── Helpers ──────────────────────────────────────────────────────────────────

function statutBadge(statut: StatutReunion) {
  const cfg = {
    en_cours:   { label: 'En cours',    cls: 'bg-blue-100 text-blue-700' },
    terminée:   { label: 'Terminée',    cls: 'bg-gray-100 text-gray-600' },
    pv_validé:  { label: 'PV validé',   cls: 'bg-green-100 text-green-700' },
  }[statut]
  return <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', cfg.cls)}>{cfg.label}</span>
}

function actionStatutBadge(statut: StatutAction) {
  const cfg = {
    en_attente: { label: 'En attente', cls: 'bg-amber-100 text-amber-700' },
    en_cours:   { label: 'En cours',   cls: 'bg-blue-100 text-blue-700' },
    réalisé:    { label: 'Réalisé',    cls: 'bg-green-100 text-green-700' },
    reporté:    { label: 'Reporté',    cls: 'bg-gray-100 text-gray-500' },
  }[statut]
  return <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', cfg.cls)}>{cfg.label}</span>
}

function prioriteBadge(p: string) {
  return p === 'urgente'
    ? <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-700">Urgente</span>
    : p === 'faible'
    ? <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">Faible</span>
    : null
}

// ─── Modal Créer Réunion ──────────────────────────────────────────────────────

function ModalCreerReunion({ onClose, onCreated }: { onClose: () => void, onCreated: (r: Reunion) => void }) {
  const [titre, setTitre] = useState('')
  const [type, setType] = useState('ordinaire')
  const [lieu, setLieu] = useState('')
  const [president, setPresident] = useState('')
  const [odj, setOdj] = useState<string[]>([''])
  const [participants, setParticipants] = useState<Participant[]>([{ nom: '', poste: '', present: true }])
  const [loading, setLoading] = useState(false)

  const addOdj = () => setOdj(prev => [...prev, ''])
  const updateOdj = (i: number, v: string) => setOdj(prev => prev.map((x, j) => j === i ? v : x))
  const removeOdj = (i: number) => setOdj(prev => prev.filter((_, j) => j !== i))

  const addParticipant = () => setParticipants(prev => [...prev, { nom: '', poste: '', present: true }])
  const updateParticipant = (i: number, key: keyof Participant, val: string | boolean) =>
    setParticipants(prev => prev.map((p, j) => j === i ? { ...p, [key]: val } : p))

  const submit = async () => {
    if (!titre.trim()) return
    setLoading(true)
    try {
      const r = await apiClient.post('/api/v1/reunions/', {
        titre, type_reunion: type, lieu, president_seance: president,
        ordre_du_jour: odj.filter(x => x.trim()),
        participants: participants.filter(p => p.nom.trim()),
      }).then(res => res.data as Reunion)
      onCreated({ ...r, type_reunion: type, date: new Date().toISOString().split('T')[0], statut: 'en_cours', nb_actions: 0, actions_en_attente: 0 })
    } catch {
      // mode démo — créer localement
      onCreated({
        reunion_id: `r-${Date.now()}`, titre, type_reunion: type, lieu, president_seance: president,
        ordre_du_jour: odj.filter(x => x.trim()),
        participants: participants.filter(p => p.nom.trim()),
        date: new Date().toISOString().split('T')[0], statut: 'en_cours', nb_actions: 0, actions_en_attente: 0,
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between p-6 border-b sticky top-0 bg-white">
          <h2 className="text-lg font-bold text-gray-900">Nouvelle réunion</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg"><XMarkIcon className="h-5 w-5" /></button>
        </div>
        <div className="p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Titre *</label>
            <input value={titre} onChange={e => setTitre(e.target.value)} placeholder="Ex. : CODIR — Arrêté des comptes"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select value={type} onChange={e => setType(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                {TYPES_REUNION.map(t => <option key={t} value={t}>{t.toUpperCase()}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Lieu</label>
              <input value={lieu} onChange={e => setLieu(e.target.value)} placeholder="Salle de réunion, visio…"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Président de séance</label>
            <input value={president} onChange={e => setPresident(e.target.value)} placeholder="Nom & fonction"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">Ordre du jour</label>
              <button onClick={addOdj} className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                <PlusIcon className="h-3.5 w-3.5" />Ajouter un point
              </button>
            </div>
            {odj.map((point, i) => (
              <div key={i} className="flex gap-2 mb-1.5">
                <span className="text-xs text-gray-400 mt-2 w-5">{i + 1}.</span>
                <input value={point} onChange={e => updateOdj(i, e.target.value)} placeholder={`Point ${i + 1}`}
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                {odj.length > 1 && (
                  <button onClick={() => removeOdj(i)} className="text-gray-400 hover:text-red-500">
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">Participants</label>
              <button onClick={addParticipant} className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                <PlusIcon className="h-3.5 w-3.5" />Ajouter
              </button>
            </div>
            {participants.map((p, i) => (
              <div key={i} className="grid grid-cols-5 gap-2 mb-1.5 items-center">
                <input value={p.nom} onChange={e => updateParticipant(i, 'nom', e.target.value)} placeholder="Nom Prénom"
                  className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                <input value={p.poste} onChange={e => updateParticipant(i, 'poste', e.target.value)} placeholder="Fonction"
                  className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
                  <input type="checkbox" checked={p.present} onChange={e => updateParticipant(i, 'present', e.target.checked)} className="rounded" />
                  Présent
                </label>
              </div>
            ))}
          </div>
        </div>
        <div className="p-6 border-t flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50">Annuler</button>
          <button onClick={submit} disabled={!titre.trim() || loading}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Création…' : 'Créer la réunion'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Panel détail réunion ─────────────────────────────────────────────────────

function PanelReunion({ reunion, onClose, onUpdated }: { reunion: Reunion, onClose: () => void, onUpdated: (r: Reunion) => void }) {
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [transcription, setTranscription] = useState(reunion.synthese ? '(transcription précédente)' : '')
  const [notes, setNotes] = useState('')
  const [analyse, setAnalyse] = useState<AnalyseResult | null>(
    reunion.synthese ? {
      synthese: reunion.synthese,
      decisions: reunion.decisions || [],
      actions: reunion.actions || [],
      points_reportes: reunion.points_reportes || [],
    } : null
  )
  const [loadingTranscript, setLoadingTranscript] = useState(false)
  const [loadingAnalyse, setLoadingAnalyse] = useState(false)
  const [loadingPV, setLoadingPV] = useState(false)
  const [loadingAgenda, setLoadingAgenda] = useState(false)
  const [agendaProchain, setAgendaProchain] = useState<Record<string, unknown> | null>(null)
  const [recordingTime, setRecordingTime] = useState(0)
  const [onglet, setOnglet] = useState<'enregistrement' | 'analyse' | 'pv' | 'agenda'>('enregistrement')

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<BlobEvent['data'][]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setAudioBlob(blob)
        stream.getTracks().forEach(t => t.stop())
      }
      recorder.start(500)
      mediaRecorderRef.current = recorder
      setIsRecording(true)
      setRecordingTime(0)
      timerRef.current = setInterval(() => setRecordingTime(t => t + 1), 1000)
    } catch {
      alert("Impossible d'accéder au microphone. Vérifiez les permissions.")
    }
  }

  const stopRecording = () => {
    mediaRecorderRef.current?.stop()
    setIsRecording(false)
    if (timerRef.current) clearInterval(timerRef.current)
  }

  const transcrire = async () => {
    if (!audioBlob && !notes.trim()) return
    setLoadingTranscript(true)
    try {
      if (audioBlob) {
        const form = new FormData()
        form.append('audio', audioBlob, 'enregistrement.webm')
        const res = await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/transcrire-audio`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        setTranscription((res.data as {transcription: string}).transcription)
      } else {
        await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/notes`, { notes })
        setTranscription(notes)
      }
      setOnglet('analyse')
    } catch {
      // démo
      const demoTranscript = `[TRANSCRIPTION DÉMO — Réunion : ${reunion.titre}]\n\nLe président de séance ouvre la séance et procède à l'appel des participants. Tous les points de l'ordre du jour sont abordés. Des décisions importantes sont prises concernant la stratégie commerciale et la conformité CIMA. Des actions sont assignées aux responsables pour les prochaines semaines.`
      setTranscription(demoTranscript)
      setOnglet('analyse')
    } finally {
      setLoadingTranscript(false)
    }
  }

  const analyser = async () => {
    setLoadingAnalyse(true)
    try {
      const res = await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/analyser`)
      const data = res.data as AnalyseResult
      setAnalyse(data)
      onUpdated({ ...reunion, synthese: data.synthese, decisions: data.decisions, actions: data.actions })
    } catch {
      // démo riche
      const demoAnalyse: AnalyseResult = {
        synthese: `La réunion "${reunion.titre}" du ${reunion.date} a permis de passer en revue les points stratégiques. Le président de séance a introduit les sujets principaux. Toutes les parties prenantes ont apporté leurs contributions. Des décisions structurantes ont été prises pour la période à venir.`,
        decisions: [
          'Validation du rapport financier Q1 2026 avec réserves sur les provisions techniques',
          'Lancement du programme de digitalisation des processus sinistres d\'ici juin 2026',
          'Approbation du budget formation CIMA pour l\'ensemble des équipes techniques',
        ],
        actions: [
          { responsable: 'Dir. Technique', description: 'Réviser les PSAP auto branche B03 et soumettre au DAF', echeance: '2026-04-25', priorite: 'urgente', statut: 'en_attente' },
          { responsable: 'Dir. Commercial', description: 'Préparer la présentation des objectifs S2 pour le prochain CODIR', echeance: '2026-05-05', priorite: 'normale', statut: 'en_attente' },
          { responsable: 'Resp. RH', description: 'Planifier les sessions de formation CIMA Book IV — Non-vie', echeance: '2026-04-30', priorite: 'normale', statut: 'en_attente' },
          { responsable: 'DAF', description: 'Transmettre les états C1-C20 à la CRCA avant la deadline', echeance: '2026-06-30', priorite: 'urgente', statut: 'en_attente' },
        ],
        points_reportes: ['Discussion sur l\'agrément nouvelle branche agriculture — reporté à mai'],
        observations: 'Séance productive. Les délais CIMA doivent être respectés en priorité.',
      }
      setAnalyse(demoAnalyse)
      onUpdated({ ...reunion, synthese: demoAnalyse.synthese, decisions: demoAnalyse.decisions, actions: demoAnalyse.actions, statut: 'terminée' })
    } finally {
      setLoadingAnalyse(false)
    }
  }

  const genererPV = async () => {
    setLoadingPV(true)
    try {
      const res = await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/pv?format=docx`)
      const { data_b64, filename } = res.data as {data_b64: string, filename: string}
      const link = document.createElement('a')
      link.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${data_b64}`
      link.download = filename || `PV_${reunion.titre.replace(/\s+/g, '_')}.docx`
      link.click()
    } catch {
      alert('PV généré (mode démo) — connectez le backend pour le téléchargement réel')
    } finally {
      setLoadingPV(false)
    }
  }

  const genererAgenda = async () => {
    setLoadingAgenda(true)
    try {
      const res = await apiClient.post(`/api/v1/reunions/${reunion.reunion_id}/agenda-prochain`)
      setAgendaProchain((res.data as {agenda: Record<string, unknown>}).agenda)
      setOnglet('agenda')
    } catch {
      setAgendaProchain({
        titre_reunion: `Suite ${reunion.titre}`,
        duree_estimee: '2h',
        ordre_du_jour: [
          { numero: 1, point: 'Suivi des actions et décisions de la réunion précédente', duree_estimee: '30min', responsable: 'Secrétaire', priorite: 'urgente' },
          { numero: 2, point: 'Point reporté : Agrément nouvelle branche agriculture', duree_estimee: '45min', responsable: 'Dir. Technique', priorite: 'normale' },
          { numero: 3, point: 'Revue états CIMA C1-C20 — préparation CRCA', duree_estimee: '30min', responsable: 'DAF', priorite: 'urgente' },
          { numero: 4, point: 'Questions diverses', duree_estimee: '15min', responsable: 'Président', priorite: 'faible' },
        ],
        documents_a_preparer: ['Tableau de suivi des actions', 'États C1-C20 provisoires', 'Dossier demande agrément'],
        notes_preparatoires: 'Rappeler aux responsables de préparer leurs tableaux de bord avant J-2.',
      })
      setOnglet('agenda')
    } finally {
      setLoadingAgenda(false)
    }
  }

  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

  const onglets: { id: 'enregistrement'|'analyse'|'pv'|'agenda', label: string, icon: React.ComponentType<{className?:string}>, disabled?: boolean }[] = [
    { id: 'enregistrement', label: 'Enregistrement & Notes', icon: MicrophoneIcon },
    { id: 'analyse', label: 'Analyse YukpoPro', icon: SparklesIcon, disabled: !transcription && !notes },
    { id: 'pv', label: 'PV & Rapport', icon: DocumentTextIcon, disabled: !analyse },
    { id: 'agenda', label: 'Agenda suivant', icon: CalendarDaysIcon, disabled: !analyse },
  ]

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="bg-white rounded-t-2xl sm:rounded-2xl w-full sm:max-w-3xl max-h-[92vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b bg-white rounded-t-2xl sm:rounded-t-2xl">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {statutBadge(reunion.statut)}
              <span className="text-xs text-gray-500">{reunion.type_reunion.toUpperCase()} — {reunion.date}</span>
            </div>
            <h2 className="text-base font-bold text-gray-900">{reunion.titre}</h2>
            {reunion.lieu && <p className="text-xs text-gray-500 mt-0.5">{reunion.lieu} {reunion.president_seance ? `• Président : ${reunion.president_seance}` : ''}</p>}
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg flex-shrink-0">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Onglets */}
        <div className="flex gap-0 border-b overflow-x-auto bg-white">
          {onglets.map(o => (
            <button key={o.id} onClick={() => !o.disabled && setOnglet(o.id as typeof onglet)}
              className={clsx(
                'flex items-center gap-1.5 px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors',
                onglet === o.id ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700',
                o.disabled && 'opacity-40 cursor-not-allowed',
              )}>
              <o.icon className="h-4 w-4" />
              {o.label}
            </button>
          ))}
        </div>

        {/* Contenu */}
        <div className="flex-1 overflow-y-auto p-5">

          {/* ── Onglet Enregistrement ── */}
          {onglet === 'enregistrement' && (
            <div className="space-y-5">
              {/* Ordre du jour */}
              {reunion.ordre_du_jour && reunion.ordre_du_jour.length > 0 && (
                <div className="bg-blue-50 rounded-xl p-4">
                  <p className="text-xs font-semibold text-blue-700 mb-2">Ordre du jour</p>
                  <ol className="space-y-1">
                    {reunion.ordre_du_jour.map((p, i) => (
                      <li key={i} className="text-sm text-blue-900 flex gap-2"><span className="text-blue-400">{i + 1}.</span>{p}</li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Enregistrement audio */}
              <div className="border border-gray-200 rounded-xl p-5">
                <p className="text-sm font-semibold text-gray-800 mb-3">Enregistrement audio en direct</p>
                <div className="flex items-center justify-center gap-4 py-4">
                  {!isRecording ? (
                    <button onClick={startRecording}
                      className="flex items-center gap-2 px-5 py-3 bg-red-600 text-white rounded-full font-medium hover:bg-red-700 shadow-lg transition-all hover:scale-105">
                      <MicrophoneIcon className="h-5 w-5" />
                      Démarrer l'enregistrement
                    </button>
                  ) : (
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-2">
                        <span className="h-3 w-3 bg-red-500 rounded-full animate-pulse" />
                        <span className="text-lg font-mono font-bold text-red-600">{formatTime(recordingTime)}</span>
                      </div>
                      <button onClick={stopRecording}
                        className="flex items-center gap-2 px-5 py-3 bg-gray-800 text-white rounded-full font-medium hover:bg-gray-900">
                        <StopIcon className="h-5 w-5" />Arrêter
                      </button>
                    </div>
                  )}
                </div>
                {audioBlob && !isRecording && (
                  <div className="flex items-center gap-3 mt-2 p-3 bg-green-50 rounded-lg">
                    <CheckCircleIcon className="h-5 w-5 text-green-600 flex-shrink-0" />
                    <span className="text-sm text-green-700">Audio enregistré ({formatTime(recordingTime)})</span>
                    <audio controls src={URL.createObjectURL(audioBlob)} className="h-8 ml-auto" />
                  </div>
                )}
              </div>

              {/* OU — Notes manuelles */}
              <div className="border border-gray-200 rounded-xl p-5">
                <p className="text-sm font-semibold text-gray-800 mb-3">Notes manuelles (si pas d'enregistrement audio)</p>
                <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={6}
                  placeholder="Saisir ici les points discutés, décisions, intervenants… YukpoPro analysera ce texte."
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-none" />
              </div>

              <button onClick={transcrire} disabled={(!audioBlob && !notes.trim()) || loadingTranscript}
                className="w-full flex items-center justify-center gap-2 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {loadingTranscript ? (
                  <><ArrowPathIcon className="h-5 w-5 animate-spin" />Transcription en cours……</>
                ) : (
                  <><SparklesIcon className="h-5 w-5" />Transcrire & analyser</>
                )}
              </button>
            </div>
          )}

          {/* ── Onglet Analyse YukpoPro ── */}
          {onglet === 'analyse' && (
            <div className="space-y-5">
              {transcription && (
                <div className="bg-gray-50 rounded-xl p-4">
                  <p className="text-xs font-semibold text-gray-600 mb-2">Transcription</p>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-5">{transcription}</p>
                </div>
              )}

              {!analyse ? (
                <button onClick={analyser} disabled={loadingAnalyse}
                  className="w-full flex items-center justify-center gap-2 py-4 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-xl font-semibold text-base hover:opacity-90 disabled:opacity-50">
                  {loadingAnalyse ? (
                    <><ArrowPathIcon className="h-5 w-5 animate-spin" />Analyse YukpoPro en cours…</>
                  ) : (
                    <><SparklesIcon className="h-5 w-5" />Analyser la réunion par IA</>
                  )}
                </button>
              ) : (
                <div className="space-y-5">
                  {/* Synthèse */}
                  <div className="bg-blue-50 rounded-xl p-4">
                    <p className="text-xs font-bold text-blue-700 uppercase mb-2">Synthèse exécutive</p>
                    <p className="text-sm text-blue-900">{analyse.synthese}</p>
                  </div>

                  {/* Décisions */}
                  {analyse.decisions.length > 0 && (
                    <div className="bg-green-50 rounded-xl p-4">
                      <p className="text-xs font-bold text-green-700 uppercase mb-2">
                        {analyse.decisions.length} Décision(s) prises
                      </p>
                      <ul className="space-y-1.5">
                        {analyse.decisions.map((d, i) => (
                          <li key={i} className="flex gap-2 text-sm text-green-900">
                            <CheckCircleIcon className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />{d}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Actions */}
                  {analyse.actions.length > 0 && (
                    <div>
                      <p className="text-xs font-bold text-gray-600 uppercase mb-2">{analyse.actions.length} Actions à suivre</p>
                      <div className="space-y-2">
                        {analyse.actions.map((a, i) => (
                          <div key={i} className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg bg-white">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-semibold text-gray-800">{a.responsable}</span>
                                {prioriteBadge(a.priorite)}
                              </div>
                              <p className="text-sm text-gray-700">{a.description}</p>
                              {a.echeance && (
                                <p className="text-xs text-gray-400 mt-1">
                                  <ClockIcon className="h-3.5 w-3.5 inline mr-1" />Échéance : {a.echeance}
                                </p>
                              )}
                            </div>
                            {actionStatutBadge(a.statut)}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Points reportés */}
                  {analyse.points_reportes.length > 0 && (
                    <div className="bg-amber-50 rounded-xl p-4">
                      <p className="text-xs font-bold text-amber-700 uppercase mb-2">Points reportés à la prochaine séance</p>
                      <ul className="space-y-1">
                        {analyse.points_reportes.map((p, i) => (
                          <li key={i} className="text-sm text-amber-900 flex gap-2">
                            <ChevronRightIcon className="h-4 w-4 flex-shrink-0" />{p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Recommandations IA */}
                  <div className="bg-purple-50 rounded-xl p-4 border border-purple-200">
                    <p className="text-xs font-bold text-purple-700 uppercase mb-2 flex items-center gap-1">
                      <SparklesIcon className="h-3.5 w-3.5" />Recommandations IA
                    </p>
                    <ul className="space-y-1.5 text-sm text-purple-900">
                      {analyse.actions.filter(a => a.priorite === 'urgente').length > 0 && (
                        <li className="flex gap-2">
                          <BellAlertIcon className="h-4 w-4 text-red-500 flex-shrink-0" />
                          {analyse.actions.filter(a => a.priorite === 'urgente').length} action(s) urgente(s) — envoyer des rappels automatiques aux responsables
                        </li>
                      )}
                      <li className="flex gap-2">
                        <CalendarDaysIcon className="h-4 w-4 text-purple-600 flex-shrink-0" />
                        Planifier la prochaine réunion dans 3–4 semaines pour le suivi des actions
                      </li>
                      {analyse.points_reportes.length > 0 && (
                        <li className="flex gap-2">
                          <ListBulletIcon className="h-4 w-4 text-purple-600 flex-shrink-0" />
                          {analyse.points_reportes.length} point(s) reporté(s) à intégrer en priorité dans le prochain ordre du jour
                        </li>
                      )}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Onglet PV ── */}
          {onglet === 'pv' && analyse && (
            <div className="space-y-5">
              <div className="bg-gray-50 rounded-xl p-5 text-center">
                <DocumentTextIcon className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                <p className="text-sm text-gray-600 mb-1">Le PV officiel contient :</p>
                <ul className="text-xs text-gray-500 space-y-0.5 mb-4">
                  <li>• Informations générales (date, lieu, participants, présences)</li>
                  <li>• Récapitulatif de chaque point de l'ordre du jour</li>
                  <li>• {analyse.decisions.length} décision(s) formelle(s)</li>
                  <li>• Tableau de suivi des {analyse.actions.length} action(s)</li>
                  <li>• Points reportés & clôture de séance</li>
                </ul>
                <div className="flex gap-3 justify-center">
                  <button onClick={genererPV} disabled={loadingPV}
                    className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50">
                    {loadingPV ? <ArrowPathIcon className="h-4 w-4 animate-spin" /> : <ArrowDownTrayIcon className="h-4 w-4" />}
                    Générer PV (Word)
                  </button>
                  <button onClick={() => genererPV()} disabled={loadingPV}
                    className="flex items-center gap-2 px-5 py-2.5 border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 disabled:opacity-50">
                    <DocumentTextIcon className="h-4 w-4" />PV (PDF)
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── Onglet Agenda suivant ── */}
          {onglet === 'agenda' && (
            <div className="space-y-5">
              {!agendaProchain ? (
                <button onClick={genererAgenda} disabled={loadingAgenda}
                  className="w-full flex items-center justify-center gap-2 py-4 bg-gradient-to-r from-green-600 to-teal-600 text-white rounded-xl font-semibold text-base hover:opacity-90 disabled:opacity-50">
                  {loadingAgenda ? (
                    <><ArrowPathIcon className="h-5 w-5 animate-spin" />Génération en cours…</>
                  ) : (
                    <><CalendarDaysIcon className="h-5 w-5" />Générer l'agenda de la prochaine réunion</>
                  )}
                </button>
              ) : (
                <div className="space-y-4">
                  <div className="bg-green-50 rounded-xl p-4">
                    <p className="text-sm font-bold text-green-800">{agendaProchain.titre_reunion as string}</p>
                    <p className="text-xs text-green-600 mt-0.5">Durée estimée : {agendaProchain.duree_estimee as string}</p>
                  </div>
                  <div>
                    <p className="text-xs font-bold text-gray-600 uppercase mb-2">Ordre du jour proposé</p>
                    <div className="space-y-2">
                      {(agendaProchain.ordre_du_jour as {numero:number,point:string,duree_estimee:string,responsable:string,priorite:string}[]).map((p, i) => (
                        <div key={i} className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg">
                          <span className="text-xs font-bold text-gray-400 w-6 flex-shrink-0 mt-0.5">{p.numero}.</span>
                          <div className="flex-1">
                            <p className="text-sm text-gray-800">{p.point}</p>
                            <p className="text-xs text-gray-400 mt-0.5">{p.responsable} · {p.duree_estimee}</p>
                          </div>
                          {p.priorite === 'urgente' && <span className="px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">Urgent</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                  {(agendaProchain.documents_a_preparer as string[]).length > 0 && (
                    <div className="bg-yellow-50 rounded-xl p-4">
                      <p className="text-xs font-bold text-yellow-700 mb-2">Documents à préparer</p>
                      <ul className="space-y-1">
                        {(agendaProchain.documents_a_preparer as string[]).map((d, i) => (
                          <li key={i} className="text-sm text-yellow-900 flex gap-2"><ChevronRightIcon className="h-4 w-4 flex-shrink-0" />{d}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <button onClick={genererPV}
                    className="w-full flex items-center justify-center gap-2 py-2.5 border border-gray-300 text-gray-700 rounded-lg text-sm hover:bg-gray-50">
                    <ArrowDownTrayIcon className="h-4 w-4" />Télécharger la convocation
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Page principale ──────────────────────────────────────────────────────────

export default function ReunionPage() {
  const [onglet, setOnglet] = useState<OngletPage>('reunions')
  const [reunions, setReunions] = useState<Reunion[]>(REUNIONS_DEMO)
  const [showCreer, setShowCreer] = useState(false)
  const [selected, setSelected] = useState<Reunion | null>(null)
  const [search, setSearch] = useState('')
  const [filtreType, setFiltreType] = useState('')
  const [filtreStatut, setFiltreStatut] = useState('')

  // Charger depuis API
  useEffect(() => {
    apiClient.get('/api/v1/reunions/').then(res => {
      const d = res.data as {reunions?: Reunion[]}
      if (d.reunions?.length) setReunions(d.reunions)
    }).catch(() => {})
  }, [])

  const filtered = reunions.filter(r =>
    (!search || r.titre.toLowerCase().includes(search.toLowerCase())) &&
    (!filtreType || r.type_reunion === filtreType) &&
    (!filtreStatut || r.statut === filtreStatut),
  )

  // Actions consolidées
  const toutesActions = reunions.flatMap(r =>
    (r.actions || []).map(a => ({ ...a, reunion_titre: r.titre, reunion_date: r.date })),
  )
  const actionsEnAttente = toutesActions.filter(a => a.statut === 'en_attente')
  const actionsUrgentes = toutesActions.filter(a => a.priorite === 'urgente' && a.statut !== 'réalisé')

  return (
    <div className="p-6 space-y-6">
      {/* En-tête */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Réunions & Agenda</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Enregistrement, transcription audio, analyse YukpoPro, PV automatisé, suivi des actions
          </p>
        </div>
        <button onClick={() => setShowCreer(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 shadow-sm">
          <PlusIcon className="h-4 w-4" />Nouvelle réunion
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Réunions ce mois', val: reunions.length, icon: UserGroupIcon, cls: 'text-blue-600 bg-blue-50' },
          { label: 'Actions en attente', val: actionsEnAttente.length, icon: ClockIcon, cls: 'text-amber-600 bg-amber-50' },
          { label: 'Actions urgentes', val: actionsUrgentes.length, icon: BellAlertIcon, cls: 'text-red-600 bg-red-50' },
          { label: 'PV validés', val: reunions.filter(r => r.statut === 'pv_validé').length, icon: CheckCircleIcon, cls: 'text-green-600 bg-green-50' },
        ].map((k, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-4">
            <div className={clsx('inline-flex p-2 rounded-lg mb-2', k.cls)}>
              <k.icon className="h-5 w-5" />
            </div>
            <p className="text-2xl font-bold text-gray-900">{k.val}</p>
            <p className="text-xs text-gray-500 mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Onglets */}
      <div className="flex gap-1 border-b">
        {[
          { id: 'reunions', label: 'Réunions', icon: UserGroupIcon },
          { id: 'actions', label: `Actions (${actionsEnAttente.length})`, icon: ChartBarIcon },
        ].map(o => (
          <button key={o.id} onClick={() => setOnglet(o.id as OngletPage)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
              onglet === o.id ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700',
            )}>
            <o.icon className="h-4 w-4" />{o.label}
          </button>
        ))}
      </div>

      {/* Onglet Réunions */}
      {onglet === 'reunions' && (
        <div className="space-y-4">
          {/* Filtres */}
          <div className="flex gap-3 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <MagnifyingGlassIcon className="h-4 w-4 absolute left-3 top-2.5 text-gray-400" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Rechercher…"
                className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
            </div>
            <select value={filtreType} onChange={e => setFiltreType(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
              <option value="">Tous types</option>
              {TYPES_REUNION.map(t => <option key={t} value={t}>{t.toUpperCase()}</option>)}
            </select>
            <select value={filtreStatut} onChange={e => setFiltreStatut(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
              <option value="">Tous statuts</option>
              <option value="en_cours">En cours</option>
              <option value="terminée">Terminée</option>
              <option value="pv_validé">PV validé</option>
            </select>
          </div>

          {/* Liste réunions */}
          <div className="space-y-3">
            {filtered.map(r => (
              <div key={r.reunion_id} onClick={() => setSelected(r)}
                className="bg-white border border-gray-200 rounded-xl p-4 hover:border-blue-300 hover:shadow-sm cursor-pointer transition-all">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {statutBadge(r.statut)}
                      <span className="text-xs text-gray-400">{r.type_reunion.toUpperCase()} · {r.date}</span>
                    </div>
                    <h3 className="text-sm font-semibold text-gray-900">{r.titre}</h3>
                    {r.lieu && <p className="text-xs text-gray-500 mt-0.5">{r.lieu}</p>}
                    {r.synthese && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{r.synthese}</p>}
                  </div>
                  <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                    {(r.actions_en_attente || 0) > 0 && (
                      <span className="flex items-center gap-1 text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded-lg">
                        <ClockIcon className="h-3.5 w-3.5" />{r.actions_en_attente} action(s)
                      </span>
                    )}
                    <ChevronRightIcon className="h-4 w-4 text-gray-400" />
                  </div>
                </div>
              </div>
            ))}
            {filtered.length === 0 && (
              <EmptyState
                icon={<UserGroupIcon className="h-10 w-10" />}
                title="Aucune réunion trouvée"
                description="Modifiez les filtres ou créez une nouvelle réunion."
              />
            )}
          </div>
        </div>
      )}

      {/* Onglet Actions */}
      {onglet === 'actions' && (
        <div className="space-y-4">
          {actionsUrgentes.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm font-bold text-red-700 mb-3 flex items-center gap-2">
                <BellAlertIcon className="h-5 w-5" />{actionsUrgentes.length} action(s) urgente(s) en attente
              </p>
              <div className="space-y-2">
                {actionsUrgentes.map((a, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-white rounded-lg border border-red-100">
                    <ExclamationTriangleIcon className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-800">{a.description}</p>
                      <p className="text-xs text-gray-500">{a.responsable} · {a.reunion_titre}</p>
                    </div>
                    {a.echeance && <span className="text-xs text-red-600 font-medium">{a.echeance}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Action</th>
                  <th className="px-4 py-3 text-left">Responsable</th>
                  <th className="px-4 py-3 text-left">Réunion</th>
                  <th className="px-4 py-3 text-left">Échéance</th>
                  <th className="px-4 py-3 text-left">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {toutesActions.map((a, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800">{a.description}</p>
                      {prioriteBadge(a.priorite)}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{a.responsable}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{a.reunion_titre}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{a.echeance || '—'}</td>
                    <td className="px-4 py-3">{actionStatutBadge(a.statut)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {toutesActions.length === 0 && (
              <EmptyState
                icon={<ListBulletIcon className="h-8 w-8" />}
                title="Aucune action à suivre"
                description="Les actions issues des réunions apparaîtront ici."
              />
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {showCreer && (
        <ModalCreerReunion
          onClose={() => setShowCreer(false)}
          onCreated={r => { setReunions(prev => [r, ...prev]); setShowCreer(false); setSelected(r) }}
        />
      )}
      {selected && (
        <PanelReunion
          reunion={selected}
          onClose={() => setSelected(null)}
          onUpdated={updated => {
            setReunions(prev => prev.map(r => r.reunion_id === updated.reunion_id ? updated : r))
            setSelected(updated)
          }}
        />
      )}
    </div>
  )
}
