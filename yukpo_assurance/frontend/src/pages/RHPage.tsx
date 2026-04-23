/**
 * RHPage — Module RH entièrement dématérialisé
 * - Registre employés
 * - Documents RH dématérialisés (contrats, bulletins, congés, formations…)
 * - Demandes digitales (congés, attestations, avances, certificats…)
 * - KPI Performance liés aux actions sur la plateforme YukpoAssurance
 * - Archive numérique RH
 */
import { useState, useCallback } from 'react'
import {
  UsersIcon, DocumentTextIcon, ClipboardDocumentCheckIcon,
  ChartBarIcon, FolderOpenIcon, MagnifyingGlassIcon,
  PlusIcon, CheckCircleIcon, XMarkIcon, ClockIcon,
  ArrowDownTrayIcon, SparklesIcon, StarIcon,
  TrophyIcon, ExclamationTriangleIcon, BriefcaseIcon,
  AcademicCapIcon, CalendarDaysIcon, BanknotesIcon,
  ShieldCheckIcon, CurrencyDollarIcon, DocumentArrowUpIcon,
  UserIcon,
} from '@heroicons/react/24/outline'
import { DemoBanner } from '../components/DemoBanner'
import { StarIcon as StarSolid } from '@heroicons/react/24/solid'
import { clsx } from 'clsx'
import { useDropzone } from 'react-dropzone'
import { ArchiveNumerique } from '../components/ArchiveNumerique'
import { RapportsModule } from '../components/RapportsModule'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, Legend,
} from 'recharts'

// ─── Types ──────────────────────────────────────────────────────────────────────

interface Employe {
  id: string
  matricule: string
  nom: string
  prenom: string
  poste: string
  departement: string
  date_embauche: string
  salaire_brut: number
  statut: 'actif' | 'conge' | 'inactif'
  email: string
  telephone?: string
  kpi_score: number   // score global 0-100
}

interface DocumentRH {
  id: string
  employe_id: string
  employe_nom: string
  type: string
  fichier: string
  date_upload: string
  periode?: string
  statut: 'disponible' | 'en_traitement' | 'archive'
}

interface DemandeRH {
  id: string
  employe_id: string
  employe_nom: string
  type: 'conge' | 'attestation' | 'avance' | 'formation' | 'certificat' | 'autre'
  description: string
  date_demande: string
  date_debut?: string
  date_fin?: string
  statut: 'en_attente' | 'approuve' | 'refuse' | 'en_traitement'
  commentaire_rh?: string
}

interface KpiEmploye {
  employe_id: string
  employe_nom: string
  departement: string
  score_global: number
  sinistres_traites: number
  contrats_emis: number
  documents_scannés: number
  reponse_moyenne_h: number
  taux_completion: number
  objectif_mensuel: number
  realise_mensuel: number
  historique: { mois: string; score: number }[]
  badges: string[]
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const EMPLOYES_DEMO: Employe[] = [
  { id: '1', matricule: 'EMP-001', nom: 'Kouassi', prenom: 'Jean-Baptiste', poste: 'Directeur Technique', departement: 'Technique', date_embauche: '2018-03-15', salaire_brut: 1_200_000, statut: 'actif', email: 'jb.kouassi@yukpo.cm', kpi_score: 91 },
  { id: '2', matricule: 'EMP-002', nom: 'Traoré', prenom: 'Fatoumata', poste: 'Responsable Sinistres', departement: 'Sinistres', date_embauche: '2019-07-01', salaire_brut: 950_000, statut: 'actif', email: 'f.traore@yukpo.cm', kpi_score: 87 },
  { id: '3', matricule: 'EMP-003', nom: 'Diallo', prenom: 'Ibrahim', poste: 'Analyste Actuaire', departement: 'Finance', date_embauche: '2020-01-15', salaire_brut: 880_000, statut: 'actif', email: 'i.diallo@yukpo.cm', kpi_score: 79 },
  { id: '4', matricule: 'EMP-004', nom: 'Bamba', prenom: 'Aminata', poste: 'Chargée de souscription', departement: 'Commercial', date_embauche: '2021-05-10', salaire_brut: 720_000, statut: 'conge', email: 'a.bamba@yukpo.cm', kpi_score: 74 },
  { id: '5', matricule: 'EMP-005', nom: 'Coulibaly', prenom: 'Seydou', poste: 'Développeur IA', departement: 'Digital', date_embauche: '2022-09-01', salaire_brut: 1_050_000, statut: 'actif', email: 's.coulibaly@yukpo.cm', kpi_score: 95 },
  { id: '6', matricule: 'EMP-006', nom: "N'Goran", prenom: 'Marie-Claire', poste: 'RH Manager', departement: 'RH', date_embauche: '2017-11-20', salaire_brut: 1_100_000, statut: 'actif', email: 'mc.ngoran@yukpo.cm', kpi_score: 88 },
]

const DOCS_RH_DEMO: DocumentRH[] = [
  { id: 'd1', employe_id: '1', employe_nom: 'Kouassi J.-B.', type: 'Contrat de travail CDI', fichier: 'contrat_EMP001_2018.pdf', date_upload: '2018-03-15', statut: 'disponible' },
  { id: 'd2', employe_id: '1', employe_nom: 'Kouassi J.-B.', type: 'Bulletin de paie', fichier: 'bulletin_EMP001_mars2026.pdf', date_upload: '2026-04-01', periode: 'Mars 2026', statut: 'disponible' },
  { id: 'd3', employe_id: '2', employe_nom: 'Traoré F.', type: 'Bulletin de paie', fichier: 'bulletin_EMP002_mars2026.pdf', date_upload: '2026-04-01', periode: 'Mars 2026', statut: 'disponible' },
  { id: 'd4', employe_id: '4', employe_nom: 'Bamba A.', type: 'Attestation congé', fichier: 'conge_EMP004_avr2026.pdf', date_upload: '2026-03-28', statut: 'disponible' },
  { id: 'd5', employe_id: '5', employe_nom: 'Coulibaly S.', type: 'Avenant contrat', fichier: 'avenant_EMP005_2024.pdf', date_upload: '2024-09-01', statut: 'disponible' },
  { id: 'd6', employe_id: '3', employe_nom: 'Diallo I.', type: 'Attestation travail', fichier: 'attestation_EMP003_avr2026.pdf', date_upload: '2026-04-09', statut: 'en_traitement' },
]

const DEMANDES_DEMO: DemandeRH[] = [
  { id: 'dem1', employe_id: '2', employe_nom: 'Traoré F.', type: 'conge', description: 'Congé annuel — 15 jours', date_demande: '2026-04-08', date_debut: '2026-04-21', date_fin: '2026-05-05', statut: 'en_attente' },
  { id: 'dem2', employe_id: '3', employe_nom: 'Diallo I.', type: 'attestation', description: 'Attestation de travail pour dossier bancaire', date_demande: '2026-04-09', statut: 'approuve', commentaire_rh: 'Document généré et remis en main propre.' },
  { id: 'dem3', employe_id: '5', employe_nom: 'Coulibaly S.', type: 'formation', description: 'Formation LLM — Fine-tuning Claude / GPT-4o (3 jours)', date_demande: '2026-04-05', date_debut: '2026-04-28', date_fin: '2026-04-30', statut: 'approuve', commentaire_rh: 'Approuvé — budget formation IT disponible.' },
  { id: 'dem4', employe_id: '1', employe_nom: 'Kouassi J.-B.', type: 'avance', description: 'Avance sur salaire — 300 000 XAF', date_demande: '2026-04-07', statut: 'refuse', commentaire_rh: 'Avance accordée en février — délai 3 mois non respecté.' },
]

const KPI_DEMO: KpiEmploye[] = [
  {
    employe_id: '5', employe_nom: 'Coulibaly Seydou', departement: 'Digital',
    score_global: 95, sinistres_traites: 0, contrats_emis: 0, documents_scannés: 142,
    reponse_moyenne_h: 0.8, taux_completion: 98, objectif_mensuel: 100, realise_mensuel: 98,
    historique: [{ mois: 'Nov', score: 88 }, { mois: 'Déc', score: 90 }, { mois: 'Jan', score: 91 }, { mois: 'Fév', score: 93 }, { mois: 'Mar', score: 95 }],
    badges: ['🏆 Top performer', '⚡ Réactivité', '🤖 IA Expert'],
  },
  {
    employe_id: '1', employe_nom: 'Kouassi Jean-Baptiste', departement: 'Technique',
    score_global: 91, sinistres_traites: 18, contrats_emis: 4, documents_scannés: 56,
    reponse_moyenne_h: 1.2, taux_completion: 95, objectif_mensuel: 20, realise_mensuel: 18,
    historique: [{ mois: 'Nov', score: 85 }, { mois: 'Déc', score: 87 }, { mois: 'Jan', score: 88 }, { mois: 'Fév', score: 90 }, { mois: 'Mar', score: 91 }],
    badges: ['🥇 Expert sinistres', '📋 Rigueur'],
  },
  {
    employe_id: '6', employe_nom: "N'Goran Marie-Claire", departement: 'RH',
    score_global: 88, sinistres_traites: 0, contrats_emis: 0, documents_scannés: 78,
    reponse_moyenne_h: 2.1, taux_completion: 91, objectif_mensuel: 30, realise_mensuel: 27,
    historique: [{ mois: 'Nov', score: 82 }, { mois: 'Déc', score: 83 }, { mois: 'Jan', score: 85 }, { mois: 'Fév', score: 86 }, { mois: 'Mar', score: 88 }],
    badges: ['👥 Leadership', '📄 Documents'],
  },
  {
    employe_id: '2', employe_nom: 'Traoré Fatoumata', departement: 'Sinistres',
    score_global: 87, sinistres_traites: 34, contrats_emis: 0, documents_scannés: 89,
    reponse_moyenne_h: 1.5, taux_completion: 92, objectif_mensuel: 35, realise_mensuel: 34,
    historique: [{ mois: 'Nov', score: 80 }, { mois: 'Déc', score: 82 }, { mois: 'Jan', score: 83 }, { mois: 'Fév', score: 85 }, { mois: 'Mar', score: 87 }],
    badges: ['🛡️ Sinistres Pro'],
  },
  {
    employe_id: '3', employe_nom: 'Diallo Ibrahim', departement: 'Finance',
    score_global: 79, sinistres_traites: 5, contrats_emis: 2, documents_scannés: 31,
    reponse_moyenne_h: 3.2, taux_completion: 78, objectif_mensuel: 15, realise_mensuel: 12,
    historique: [{ mois: 'Nov', score: 74 }, { mois: 'Déc', score: 75 }, { mois: 'Jan', score: 76 }, { mois: 'Fév', score: 77 }, { mois: 'Mar', score: 79 }],
    badges: ['📊 Actuariat'],
  },
  {
    employe_id: '4', employe_nom: 'Bamba Aminata', departement: 'Commercial',
    score_global: 74, sinistres_traites: 0, contrats_emis: 12, documents_scannés: 45,
    reponse_moyenne_h: 2.8, taux_completion: 74, objectif_mensuel: 20, realise_mensuel: 15,
    historique: [{ mois: 'Nov', score: 70 }, { mois: 'Déc', score: 71 }, { mois: 'Jan', score: 72 }, { mois: 'Fév', score: 73 }, { mois: 'Mar', score: 74 }],
    badges: ['💼 Commercial'],
  },
]

const TYPES_DOCUMENT_RH = [
  'Contrat de travail CDI', 'Contrat de travail CDD', 'Avenant contrat',
  'Bulletin de paie', 'Attestation travail', 'Attestation congé',
  'Certificat médical', 'Déclaration CNPS', 'Fiche de poste',
  'Évaluation annuelle', 'Ordre de mission', 'Note de frais',
  'Diplôme / Certificat', 'Autre document RH',
]

const TYPES_DEMANDE = [
  { key: 'conge',       label: 'Congé',                icon: CalendarDaysIcon,    couleur: 'text-blue-600 bg-blue-50' },
  { key: 'attestation', label: 'Attestation',           icon: DocumentTextIcon,    couleur: 'text-green-600 bg-green-50' },
  { key: 'avance',      label: 'Avance sur salaire',    icon: BanknotesIcon,       couleur: 'text-amber-600 bg-amber-50' },
  { key: 'formation',   label: 'Formation',             icon: AcademicCapIcon,     couleur: 'text-purple-600 bg-purple-50' },
  { key: 'certificat',  label: 'Certificat médical',    icon: ShieldCheckIcon,     couleur: 'text-red-600 bg-red-50' },
  { key: 'autre',       label: 'Autre',                 icon: BriefcaseIcon,       couleur: 'text-gray-600 bg-gray-50' },
]

// ─── Helpers ───────────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 90 ? 'bg-green-100 text-green-700 border-green-300' :
    score >= 75 ? 'bg-blue-100 text-blue-700 border-blue-300' :
    score >= 60 ? 'bg-amber-100 text-amber-700 border-amber-300' :
    'bg-red-100 text-red-700 border-red-300'
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-sm font-bold border', cls)}>
      <TrophyIcon className="h-3.5 w-3.5" />
      {score}/100
    </span>
  )
}

// ─── Onglet Registre employés ─────────────────────────────────────────────────

function OngletRegistre() {
  const [search, setSearch] = useState('')
  const [filtreDept, setFiltreDept] = useState('')
  const [selected, setSelected] = useState<Employe | null>(null)

  const depts = [...new Set(EMPLOYES_DEMO.map(e => e.departement))]
  const filtered = EMPLOYES_DEMO.filter(e => {
    const q = search.toLowerCase()
    return (!search || `${e.nom} ${e.prenom} ${e.matricule}`.toLowerCase().includes(q)) &&
      (!filtreDept || e.departement === filtreDept)
  })

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Effectif total', value: EMPLOYES_DEMO.length, cls: 'text-blue-700 bg-blue-50 border-blue-200' },
          { label: 'Actifs', value: EMPLOYES_DEMO.filter(e => e.statut === 'actif').length, cls: 'text-green-700 bg-green-50 border-green-200' },
          { label: 'En congé', value: EMPLOYES_DEMO.filter(e => e.statut === 'conge').length, cls: 'text-amber-700 bg-amber-50 border-amber-200' },
          { label: 'Score KPI moyen', value: `${Math.round(EMPLOYES_DEMO.reduce((a, e) => a + e.kpi_score, 0) / EMPLOYES_DEMO.length)}/100`, cls: 'text-purple-700 bg-purple-50 border-purple-200' },
        ].map((k, i) => (
          <div key={i} className={clsx('border rounded-xl p-4 text-center', k.cls)}>
            <p className="text-2xl font-bold">{k.value}</p>
            <p className="text-xs mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Filtres */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
            placeholder="Rechercher un employé…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <select className="px-3 py-2 border border-gray-300 rounded-lg text-sm" value={filtreDept} onChange={e => setFiltreDept(e.target.value)}>
          <option value="">Tous départements</option>
          {depts.map(d => <option key={d}>{d}</option>)}
        </select>
        <button className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors">
          <PlusIcon className="h-4 w-4" /> Nouvel employé
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              {['Matricule', 'Nom & Prénom', 'Poste', 'Département', 'Score KPI', 'Statut', 'Actions'].map(h => (
                <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map(e => (
              <tr key={e.id} className="hover:bg-gray-50 transition-colors">
                <td className="py-3 px-4 font-mono text-primary-600 text-xs font-semibold">{e.matricule}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                      {e.prenom[0]}{e.nom[0]}
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{e.prenom} {e.nom}</p>
                      <p className="text-xs text-gray-400">{e.email}</p>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-4 text-gray-700">{e.poste}</td>
                <td className="py-3 px-4">
                  <span className="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded">{e.departement}</span>
                </td>
                <td className="py-3 px-4"><ScoreBadge score={e.kpi_score} /></td>
                <td className="py-3 px-4">
                  <span className={clsx('px-2 py-1 rounded-full text-xs font-medium',
                    e.statut === 'actif' ? 'bg-green-100 text-green-700' :
                    e.statut === 'conge' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'
                  )}>
                    {e.statut === 'actif' ? 'Actif' : e.statut === 'conge' ? 'En congé' : 'Inactif'}
                  </span>
                </td>
                <td className="py-3 px-4">
                  <button onClick={() => setSelected(e)} className="text-xs text-primary-600 hover:underline font-medium">Voir dossier</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal dossier employé */}
      {selected && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center text-white font-bold">
                  {selected.prenom[0]}{selected.nom[0]}
                </div>
                <div>
                  <h3 className="font-bold text-gray-900">{selected.prenom} {selected.nom}</h3>
                  <p className="text-sm text-gray-500">{selected.poste} — {selected.departement}</p>
                </div>
              </div>
              <button onClick={() => setSelected(null)} className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              {[
                ['Matricule', selected.matricule],
                ['Email', selected.email],
                ['Date d\'embauche', selected.date_embauche],
                ['Salaire brut', `${selected.salaire_brut.toLocaleString('fr-FR')} FCFA`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between text-sm">
                  <span className="text-gray-500">{k}</span>
                  <span className="font-medium text-gray-900">{v}</span>
                </div>
              ))}
              <div className="pt-2 border-t border-gray-100">
                <p className="text-xs text-gray-400 mb-1">Score KPI actuel</p>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-gray-100 rounded-full h-2">
                    <div className={clsx('h-2 rounded-full transition-all', selected.kpi_score >= 85 ? 'bg-green-500' : selected.kpi_score >= 70 ? 'bg-blue-500' : 'bg-amber-500')} style={{ width: `${selected.kpi_score}%` }} />
                  </div>
                  <ScoreBadge score={selected.kpi_score} />
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <button className="flex-1 text-sm bg-primary-600 text-white px-3 py-2 rounded-lg hover:bg-primary-700 transition-colors font-medium">
                  Documents ({DOCS_RH_DEMO.filter(d => d.employe_id === selected.id).length})
                </button>
                <button className="flex-1 text-sm bg-gray-100 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-200 transition-colors font-medium">
                  Bulletin de paie
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Onglet Documents RH ──────────────────────────────────────────────────────

function OngletDocuments() {
  const [docs, setDocs] = useState<DocumentRH[]>(DOCS_RH_DEMO)
  const [filterType, setFilterType] = useState('')
  const [filterEmploye, setFilterEmploye] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const [uploadForm, setUploadForm] = useState({ employe_id: '', type: TYPES_DOCUMENT_RH[0], periode: '' })
  const [uploading, setUploading] = useState(false)

  const onDrop = useCallback(async (files: File[]) => {
    if (!uploadForm.employe_id) { alert('Sélectionnez un employé'); return }
    setUploading(true)
    for (const f of files) {
      const employe = EMPLOYES_DEMO.find(e => e.id === uploadForm.employe_id)
      const nouveau: DocumentRH = {
        id: Date.now().toString(),
        employe_id: uploadForm.employe_id,
        employe_nom: employe ? `${employe.prenom} ${employe.nom}` : 'Inconnu',
        type: uploadForm.type,
        fichier: f.name,
        date_upload: new Date().toLocaleDateString('fr-FR'),
        periode: uploadForm.periode || undefined,
        statut: 'en_traitement',
      }
      setDocs(prev => [nouveau, ...prev])
      await new Promise(r => setTimeout(r, 800))
      setDocs(prev => prev.map(d => d.id === nouveau.id ? { ...d, statut: 'disponible' as const } : d))
    }
    setUploading(false)
    setShowUpload(false)
  }, [uploadForm])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, multiple: false })

  const filtered = docs.filter(d =>
    (!filterType || d.type === filterType) &&
    (!filterEmploye || d.employe_nom.toLowerCase().includes(filterEmploye.toLowerCase()))
  )

  const statutCls = (s: string) => ({
    disponible:    'bg-green-100 text-green-700',
    en_traitement: 'bg-amber-100 text-amber-700',
    archive:       'bg-gray-100 text-gray-600',
  }[s] ?? 'bg-gray-100 text-gray-600')

  return (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap">
        <input className="px-3 py-2 border border-gray-300 rounded-lg text-sm flex-1 min-w-40"
          placeholder="Filtrer par employé…" value={filterEmploye} onChange={e => setFilterEmploye(e.target.value)} />
        <select className="px-3 py-2 border border-gray-300 rounded-lg text-sm" value={filterType} onChange={e => setFilterType(e.target.value)}>
          <option value="">Tous types</option>
          {TYPES_DOCUMENT_RH.map(t => <option key={t}>{t}</option>)}
        </select>
        <button onClick={() => setShowUpload(!showUpload)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors">
          <DocumentArrowUpIcon className="h-4 w-4" />
          {showUpload ? 'Fermer' : 'Ajouter un document'}
        </button>
      </div>

      {/* Zone upload */}
      {showUpload && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 space-y-3">
          <h4 className="text-sm font-semibold text-gray-700">Ajouter un document RH</h4>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Employé *</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                value={uploadForm.employe_id} onChange={e => setUploadForm(p => ({ ...p, employe_id: e.target.value }))}>
                <option value="">Sélectionner…</option>
                {EMPLOYES_DEMO.map(e => <option key={e.id} value={e.id}>{e.prenom} {e.nom}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Type de document</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                value={uploadForm.type} onChange={e => setUploadForm(p => ({ ...p, type: e.target.value }))}>
                {TYPES_DOCUMENT_RH.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Période (si applicable)</label>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                placeholder="Ex: Mars 2026" value={uploadForm.periode} onChange={e => setUploadForm(p => ({ ...p, periode: e.target.value }))} />
            </div>
          </div>
          <div {...getRootProps()} className={clsx('border-2 border-dashed rounded-xl p-8 text-center cursor-pointer',
            isDragActive ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-primary-400')}>
            <input {...getInputProps()} />
            {uploading ? (
              <div className="space-y-2">
                <div className="animate-spin h-6 w-6 border-2 border-primary-500 border-t-transparent rounded-full mx-auto" />
                <p className="text-sm text-gray-500">Upload en cours…</p>
              </div>
            ) : (
              <>
                <DocumentArrowUpIcon className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                <p className="text-sm text-gray-600 font-medium">Glissez le fichier ou cliquez</p>
                <p className="text-xs text-gray-400 mt-1">PDF, DOCX, XLSX — max 20 Mo</p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Liste */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wide">
          {filtered.length} document{filtered.length > 1 ? 's' : ''}
        </div>
        <div className="divide-y divide-gray-100">
          {filtered.map(d => (
            <div key={d.id} className="flex items-center gap-4 px-5 py-3 hover:bg-gray-50 transition-colors">
              <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0">
                <DocumentTextIcon className="h-4 w-4 text-blue-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{d.fichier}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-gray-500">{d.type}</span>
                  <span className="text-gray-300">·</span>
                  <span className="text-xs text-primary-600 font-medium">{d.employe_nom}</span>
                  {d.periode && <><span className="text-gray-300">·</span><span className="text-xs text-gray-400">{d.periode}</span></>}
                </div>
              </div>
              <span className="text-xs text-gray-400">{d.date_upload}</span>
              <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', statutCls(d.statut))}>
                {d.statut === 'disponible' ? 'Disponible' : d.statut === 'en_traitement' ? 'En traitement' : 'Archivé'}
              </span>
              <div className="flex gap-1">
                <button className="p-1.5 rounded-lg text-gray-400 hover:text-primary-600 hover:bg-primary-50 transition-colors">
                  <ArrowDownTrayIcon className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="text-center py-12 text-gray-400 text-sm">Aucun document trouvé</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Onglet Demandes RH ───────────────────────────────────────────────────────

function OngletDemandes() {
  const [demandes, setDemandes] = useState<DemandeRH[]>(DEMANDES_DEMO)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ employe_id: '', type: 'conge' as DemandeRH['type'], description: '', date_debut: '', date_fin: '' })
  const [filtre, setFiltre] = useState<'tous' | DemandeRH['statut']>('tous')
  const [commentaire, setCommentaire] = useState<Record<string, string>>({})

  const filtrees = demandes.filter(d => filtre === 'tous' || d.statut === filtre)
  const enAttente = demandes.filter(d => d.statut === 'en_attente').length

  const traiter = (id: string, statut: 'approuve' | 'refuse') => {
    setDemandes(prev => prev.map(d =>
      d.id === id ? { ...d, statut, commentaire_rh: commentaire[id] || undefined } : d
    ))
  }

  const soumettre = () => {
    const employe = EMPLOYES_DEMO.find(e => e.id === form.employe_id)
    if (!employe || !form.description) return
    setDemandes(prev => [{
      id: Date.now().toString(),
      employe_id: form.employe_id,
      employe_nom: `${employe.prenom} ${employe.nom}`,
      type: form.type,
      description: form.description,
      date_demande: new Date().toLocaleDateString('fr-FR'),
      date_debut: form.date_debut || undefined,
      date_fin: form.date_fin || undefined,
      statut: 'en_attente',
    }, ...prev])
    setShowForm(false)
    setForm({ employe_id: '', type: 'conge', description: '', date_debut: '', date_fin: '' })
  }

  const statutCls = (s: DemandeRH['statut']) => ({
    en_attente:    'bg-amber-100 text-amber-700',
    approuve:      'bg-green-100 text-green-700',
    refuse:        'bg-red-100 text-red-700',
    en_traitement: 'bg-blue-100 text-blue-700',
  }[s])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2 flex-wrap">
          {([
            { k: 'tous', l: 'Toutes' },
            { k: 'en_attente', l: `En attente (${enAttente})` },
            { k: 'approuve', l: 'Approuvées' },
            { k: 'refuse', l: 'Refusées' },
          ] as const).map(({ k, l }) => (
            <button key={k} onClick={() => setFiltre(k)}
              className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                filtre === k ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}>
              {l}
            </button>
          ))}
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors">
          <PlusIcon className="h-4 w-4" />
          Nouvelle demande
        </button>
      </div>

      {/* Formulaire nouvelle demande */}
      {showForm && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-5 space-y-4">
          <h4 className="text-sm font-semibold text-gray-700">Nouvelle demande RH</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Employé *</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                value={form.employe_id} onChange={e => setForm(p => ({ ...p, employe_id: e.target.value }))}>
                <option value="">Sélectionner…</option>
                {EMPLOYES_DEMO.map(e => <option key={e.id} value={e.id}>{e.prenom} {e.nom}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Type de demande</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value as DemandeRH['type'] }))}>
                {TYPES_DEMANDE.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>
            {(form.type === 'conge' || form.type === 'formation') && (<>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Date début</label>
                <input type="date" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  value={form.date_debut} onChange={e => setForm(p => ({ ...p, date_debut: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Date fin</label>
                <input type="date" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  value={form.date_fin} onChange={e => setForm(p => ({ ...p, date_fin: e.target.value }))} />
              </div>
            </>)}
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Description *</label>
              <textarea className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-none" rows={2}
                placeholder="Motif, précisions…" value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">Annuler</button>
            <button onClick={soumettre} className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 font-semibold">Soumettre</button>
          </div>
        </div>
      )}

      {/* Liste demandes */}
      <div className="space-y-3">
        {filtrees.map(d => {
          const typeCfg = TYPES_DEMANDE.find(t => t.key === d.type)!
          const Icon = typeCfg.icon
          return (
            <div key={d.id} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-start gap-3">
                <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0', typeCfg.couleur)}>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-gray-900 text-sm">{d.employe_nom}</span>
                    <span className="text-xs text-gray-400">·</span>
                    <span className="text-xs font-medium text-gray-600">{typeCfg.label}</span>
                    <span className="text-xs text-gray-400">· {d.date_demande}</span>
                  </div>
                  <p className="text-sm text-gray-600 mt-1">{d.description}</p>
                  {(d.date_debut || d.date_fin) && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {d.date_debut} {d.date_fin ? `→ ${d.date_fin}` : ''}
                    </p>
                  )}
                  {d.commentaire_rh && (
                    <p className="text-xs text-gray-500 mt-1 italic bg-gray-50 rounded px-2 py-1">
                      RH : {d.commentaire_rh}
                    </p>
                  )}
                </div>
                <span className={clsx('px-2 py-1 rounded-full text-xs font-medium flex-shrink-0', statutCls(d.statut))}>
                  {d.statut === 'en_attente' ? 'En attente' : d.statut === 'approuve' ? 'Approuvé' : d.statut === 'refuse' ? 'Refusé' : 'En traitement'}
                </span>
              </div>
              {d.statut === 'en_attente' && (
                <div className="mt-3 flex gap-2 items-end">
                  <input className="flex-1 px-3 py-1.5 text-xs border border-gray-300 rounded-lg"
                    placeholder="Commentaire RH (optionnel)…"
                    value={commentaire[d.id] ?? ''} onChange={e => setCommentaire(p => ({ ...p, [d.id]: e.target.value }))} />
                  <button onClick={() => traiter(d.id, 'approuve')} className="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg font-semibold hover:bg-green-700">
                    ✓ Approuver
                  </button>
                  <button onClick={() => traiter(d.id, 'refuse')} className="px-3 py-1.5 bg-red-100 text-red-700 text-xs rounded-lg font-semibold hover:bg-red-200">
                    ✕ Refuser
                  </button>
                </div>
              )}
            </div>
          )
        })}
        {filtrees.length === 0 && <p className="text-center text-gray-400 text-sm py-8">Aucune demande</p>}
      </div>
    </div>
  )
}

// ─── Onglet KPI Performance ───────────────────────────────────────────────────

function OngletKPI() {
  const [selected, setSelected] = useState<KpiEmploye>(KPI_DEMO[0])

  const radarData = [
    { axe: 'Dossiers', value: Math.round(selected.taux_completion * 0.95) },
    { axe: 'Réactivité', value: Math.max(0, 100 - selected.reponse_moyenne_h * 20) },
    { axe: 'Documents', value: Math.min(100, selected.documents_scannés) },
    { axe: 'Objectifs', value: Math.round((selected.realise_mensuel / selected.objectif_mensuel) * 100) },
    { axe: 'Qualité', value: selected.score_global },
    { axe: 'Présence', value: 90 },
  ]

  return (
    <div className="space-y-6">
      {/* Info transparence */}
      <div className="bg-gradient-to-r from-primary-50 to-blue-50 border border-primary-200 rounded-xl p-4 flex items-start gap-3">
        <SparklesIcon className="h-5 w-5 text-primary-600 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-primary-900">KPI Performance — Objectif transparence totale</p>
          <p className="text-xs text-primary-700 mt-1">
            Les scores sont calculés automatiquement à partir des actions réelles sur YukpoAssurance : sinistres traités, contrats émis, documents scannés, temps de réponse, taux de completion d'objectifs. Les primes de performance sont ainsi objectives et vérifiables par tous.
          </p>
        </div>
      </div>

      {/* Classement global */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">Classement Performance — {new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })}</h3>
        </div>
        <div className="divide-y divide-gray-100">
          {KPI_DEMO.map((k, i) => (
            <div
              key={k.employe_id}
              className={clsx('px-5 py-3 flex items-center gap-4 cursor-pointer transition-colors',
                selected.employe_id === k.employe_id ? 'bg-primary-50' : 'hover:bg-gray-50'
              )}
              onClick={() => setSelected(k)}
            >
              {/* Rang */}
              <div className={clsx('w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0',
                i === 0 ? 'bg-yellow-100 text-yellow-700' : i === 1 ? 'bg-gray-100 text-gray-600' : i === 2 ? 'bg-orange-100 text-orange-600' : 'bg-gray-50 text-gray-400'
              )}>
                {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900 text-sm">{k.employe_nom}</p>
                <p className="text-xs text-gray-400">{k.departement}</p>
              </div>
              {/* KPI détail */}
              <div className="hidden md:flex gap-4 text-xs text-gray-500">
                <span title="Sinistres traités">🛡 {k.sinistres_traites}</span>
                <span title="Contrats émis">📋 {k.contrats_emis}</span>
                <span title="Documents scannés">📄 {k.documents_scannés}</span>
                <span title="Réponse moy.">⚡ {k.reponse_moyenne_h}h</span>
              </div>
              {/* Barre + score */}
              <div className="flex items-center gap-2 min-w-32">
                <div className="flex-1 bg-gray-100 rounded-full h-2">
                  <div
                    className={clsx('h-2 rounded-full', k.score_global >= 90 ? 'bg-green-500' : k.score_global >= 75 ? 'bg-blue-500' : 'bg-amber-500')}
                    style={{ width: `${k.score_global}%` }}
                  />
                </div>
                <ScoreBadge score={k.score_global} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Détail employé sélectionné */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Radar */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h4 className="font-semibold text-gray-900 mb-1">{selected.employe_nom}</h4>
          <p className="text-xs text-gray-400 mb-4">{selected.departement} · {selected.badges.join(' · ')}</p>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={radarData}>
              <PolarGrid />
              <PolarAngleAxis dataKey="axe" tick={{ fontSize: 11 }} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
              <Radar name="Score" dataKey="value" stroke="#1d4ed8" fill="#3b82f6" fillOpacity={0.3} />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* Évolution + KPIs détaillés */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h4 className="font-semibold text-gray-900 mb-3">Évolution score (5 derniers mois)</h4>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={selected.historique} barSize={24}>
                <XAxis dataKey="mois" tick={{ fontSize: 11 }} />
                <YAxis domain={[50, 100]} hide />
                <Tooltip formatter={(v) => [`${v}/100`, 'Score']} />
                <Bar dataKey="score" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 grid grid-cols-2 gap-3">
            {[
              { label: 'Sinistres traités', value: selected.sinistres_traites, icon: '🛡️' },
              { label: 'Contrats émis', value: selected.contrats_emis, icon: '📋' },
              { label: 'Documents scannés', value: selected.documents_scannés, icon: '📄' },
              { label: 'Temps réponse moy.', value: `${selected.reponse_moyenne_h}h`, icon: '⚡' },
              { label: 'Taux completion', value: `${selected.taux_completion}%`, icon: '✅' },
              { label: 'Objectif mensuel', value: `${selected.realise_mensuel}/${selected.objectif_mensuel}`, icon: '🎯' },
            ].map((m, i) => (
              <div key={i} className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">{m.icon} {m.label}</p>
                <p className="font-bold text-gray-900">{m.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Portail Employé ──────────────────────────────────────────────────────────
// Vue restreinte : l'employé voit uniquement ses propres données et peut
// soumettre des demandes. Il ne peut pas accéder au registre global ni aux KPI.

const MOI: Employe = EMPLOYES_DEMO[1] // Simuler l'employé connecté (Traoré F.)

function PortailEmploye() {
  const mesDocs = DOCS_RH_DEMO.filter(d => d.employe_id === MOI.id)
  const mesDemandes = DEMANDES_DEMO.filter(d => d.employe_id === MOI.id)
  const [onglet, setOnglet] = useState<'accueil' | 'demandes' | 'documents'>('accueil')
  const [showNouvelledemande, setShowNouvelledemande] = useState(false)
  const [typeDemande, setTypeDemande] = useState<DemandeRH['type']>('conge')
  const [description, setDescription] = useState('')
  const [dateDebut, setDateDebut] = useState('')
  const [dateFin, setDateFin] = useState('')
  const [demandes, setDemandes] = useState<DemandeRH[]>(mesDemandes)
  const [submitting, setSubmitting] = useState(false)

  const soumettreDemande = async () => {
    if (!description.trim()) return
    setSubmitting(true)
    await new Promise(r => setTimeout(r, 800))
    const nouvelle: DemandeRH = {
      id: `dem-${Date.now()}`,
      employe_id: MOI.id,
      employe_nom: `${MOI.prenom} ${MOI.nom}`,
      type: typeDemande,
      description,
      date_demande: new Date().toISOString().split('T')[0],
      date_debut: dateDebut || undefined,
      date_fin: dateFin || undefined,
      statut: 'en_attente',
    }
    setDemandes(prev => [nouvelle, ...prev])
    setShowNouvelledemande(false)
    setDescription('')
    setDateDebut('')
    setDateFin('')
    setSubmitting(false)
    setOnglet('demandes')
  }

  const statutColor = (s: DemandeRH['statut']) => ({
    en_attente:   'bg-amber-100 text-amber-700',
    approuve:     'bg-green-100 text-green-700',
    refuse:       'bg-red-100 text-red-700',
    en_traitement:'bg-blue-100 text-blue-700',
  }[s])

  const statutLabel = (s: DemandeRH['statut']) => ({
    en_attente: 'En attente',
    approuve: 'Approuvé',
    refuse: 'Refusé',
    en_traitement: 'En traitement',
  }[s])

  return (
    <div className="space-y-5">
      {/* Carte profil */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-2xl p-5 text-white">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-white/20 flex items-center justify-center text-xl font-bold">
            {MOI.prenom[0]}{MOI.nom[0]}
          </div>
          <div>
            <p className="text-xl font-bold">{MOI.prenom} {MOI.nom}</p>
            <p className="text-blue-200 text-sm">{MOI.poste} · {MOI.departement}</p>
            <p className="text-blue-200 text-xs mt-0.5">{MOI.matricule} · {MOI.email}</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-4">
          {[
            { label: 'Score KPI', val: `${MOI.kpi_score}/100` },
            { label: 'Mes demandes', val: demandes.length },
            { label: 'Docs disponibles', val: mesDocs.length },
          ].map((k, i) => (
            <div key={i} className="bg-white/10 rounded-xl p-3 text-center">
              <p className="text-lg font-bold">{k.val}</p>
              <p className="text-xs text-blue-200">{k.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Onglets portail employé */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {[
          { id: 'accueil', label: 'Accueil', icon: SparklesIcon },
          { id: 'demandes', label: `Mes demandes (${demandes.length})`, icon: ClipboardDocumentCheckIcon },
          { id: 'documents', label: 'Mes documents', icon: DocumentTextIcon },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id as typeof onglet)}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              onglet === id ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
            <Icon className="h-4 w-4" />{label}
          </button>
        ))}
      </div>

      {/* Accueil */}
      {onglet === 'accueil' && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Bienvenue dans votre espace RH personnel. Faites vos demandes administratives en quelques clics.</p>
          <div className="grid grid-cols-2 gap-3">
            {TYPES_DEMANDE.map(({ key, label, icon: Icon, couleur }) => (
              <button key={key} onClick={() => { setTypeDemande(key as DemandeRH['type']); setShowNouvelledemande(true) }}
                className={clsx('flex items-center gap-3 p-4 rounded-xl border-2 border-transparent text-left transition-all hover:shadow-md hover:scale-105', couleur.replace('text-', 'border-').replace('bg-', 'bg-'))}>
                <div className={clsx('p-2 rounded-lg', couleur)}>
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-gray-900">{label}</p>
                  <p className="text-xs text-gray-400">Soumettre une demande</p>
                </div>
              </button>
            ))}
          </div>
          {demandes.filter(d => d.statut === 'en_attente').length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-amber-700 mb-2">
                {demandes.filter(d => d.statut === 'en_attente').length} demande(s) en cours de traitement
              </p>
              {demandes.filter(d => d.statut === 'en_attente').map(d => (
                <div key={d.id} className="text-xs text-amber-700 flex gap-2 items-center">
                  <ClockIcon className="h-3.5 w-3.5" />{d.description} · Soumis le {d.date_demande}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Mes demandes */}
      {onglet === 'demandes' && (
        <div className="space-y-3">
          <button onClick={() => setShowNouvelledemande(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700">
            <PlusIcon className="h-4 w-4" />Nouvelle demande
          </button>
          {demandes.map(d => (
            <div key={d.id} className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', statutColor(d.statut))}>
                      {statutLabel(d.statut)}
                    </span>
                    <span className="text-xs text-gray-400">{d.type} · {d.date_demande}</span>
                  </div>
                  <p className="text-sm font-medium text-gray-800">{d.description}</p>
                  {(d.date_debut || d.date_fin) && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {d.date_debut} {d.date_fin ? `→ ${d.date_fin}` : ''}
                    </p>
                  )}
                  {d.commentaire_rh && (
                    <div className="mt-2 bg-gray-50 rounded-lg p-2">
                      <p className="text-xs text-gray-500 font-medium">Commentaire RH :</p>
                      <p className="text-xs text-gray-700">{d.commentaire_rh}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          {demandes.length === 0 && (
            <div className="text-center py-10 text-gray-400 text-sm">Aucune demande pour le moment</div>
          )}
        </div>
      )}

      {/* Mes documents */}
      {onglet === 'documents' && (
        <div className="space-y-3">
          {mesDocs.map(d => (
            <div key={d.id} className="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4">
              <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0">
                <DocumentTextIcon className="h-5 w-5 text-blue-600" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-800">{d.type}</p>
                <p className="text-xs text-gray-400">{d.fichier} · {d.date_upload}</p>
                {d.periode && <p className="text-xs text-gray-400">Période : {d.periode}</p>}
              </div>
              <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium',
                d.statut === 'disponible' ? 'bg-green-100 text-green-700' :
                d.statut === 'en_traitement' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-500')}>
                {d.statut === 'disponible' ? 'Disponible' : d.statut === 'en_traitement' ? 'En traitement' : 'Archivé'}
              </span>
              {d.statut === 'disponible' && (
                <button className="p-1.5 hover:bg-gray-100 rounded-lg">
                  <ArrowDownTrayIcon className="h-4 w-4 text-gray-400" />
                </button>
              )}
            </div>
          ))}
          {mesDocs.length === 0 && (
            <div className="text-center py-10 text-gray-400 text-sm">Aucun document disponible</div>
          )}
        </div>
      )}

      {/* Modal nouvelle demande */}
      {showNouvelledemande && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b">
              <h3 className="font-bold text-gray-900">Nouvelle demande</h3>
              <button onClick={() => setShowNouvelledemande(false)} className="p-1.5 hover:bg-gray-100 rounded-lg">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Type de demande</label>
                <div className="grid grid-cols-3 gap-2">
                  {TYPES_DEMANDE.map(({ key, label, icon: Icon, couleur }) => (
                    <button key={key} onClick={() => setTypeDemande(key as DemandeRH['type'])}
                      className={clsx('flex flex-col items-center gap-1 p-2 rounded-lg border-2 text-xs font-medium transition-all',
                        typeDemande === key ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600 hover:border-gray-300')}>
                      <Icon className="h-5 w-5" />
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description *</label>
                <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3}
                  placeholder="Décrivez votre demande en quelques mots…"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 outline-none resize-none" />
              </div>
              {(typeDemande === 'conge' || typeDemande === 'formation') && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Date début</label>
                    <input type="date" value={dateDebut} onChange={e => setDateDebut(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 outline-none" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Date fin</label>
                    <input type="date" value={dateFin} onChange={e => setDateFin(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 outline-none" />
                  </div>
                </div>
              )}
              {/* Circuit de validation */}
              <div className="bg-blue-50 rounded-xl p-3">
                <p className="text-xs font-semibold text-blue-700 mb-1">Circuit de validation</p>
                <div className="flex items-center gap-2 text-xs text-blue-600">
                  <span className="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center font-bold">1</span>
                  Vous → Responsable hiérarchique
                  <span className="mx-1">→</span>
                  <span className="w-5 h-5 bg-blue-100 rounded-full flex items-center justify-center font-bold">2</span>
                  Service RH
                </div>
              </div>
            </div>
            <div className="p-5 border-t flex justify-end gap-3">
              <button onClick={() => setShowNouvelledemande(false)}
                className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50">Annuler</button>
              <button onClick={soumettreDemande} disabled={!description.trim() || submitting}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50">
                {submitting ? 'Envoi…' : 'Soumettre'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Dashboard RH Service — Validation des demandes ──────────────────────────

function OngletValidationDemandes() {
  const [demandes, setDemandes] = useState<DemandeRH[]>(DEMANDES_DEMO)
  const [selected, setSelected] = useState<DemandeRH | null>(null)
  const [commentaire, setCommentaire] = useState('')
  const [traitant, setTraitant] = useState(false)

  const valider = async (statut: 'approuve' | 'refuse') => {
    if (!selected) return
    setTraitant(true)
    await new Promise(r => setTimeout(r, 600))
    setDemandes(prev => prev.map(d => d.id === selected.id
      ? { ...d, statut, commentaire_rh: commentaire || undefined }
      : d))
    setSelected(null)
    setCommentaire('')
    setTraitant(false)
  }

  const enAttente = demandes.filter(d => d.statut === 'en_attente')
  const traitees = demandes.filter(d => d.statut !== 'en_attente')

  return (
    <div className="space-y-4">
      {enAttente.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-sm font-bold text-amber-800 mb-3">
            {enAttente.length} demande(s) en attente de validation
          </p>
          <div className="space-y-2">
            {enAttente.map(d => {
              const typeInfo = TYPES_DEMANDE.find(t => t.key === d.type)
              const Icon = typeInfo?.icon || ClipboardDocumentCheckIcon
              return (
                <div key={d.id} className="bg-white rounded-xl p-4 border border-amber-100">
                  <div className="flex items-start gap-3">
                    <div className={clsx('p-2 rounded-lg flex-shrink-0', typeInfo?.couleur || 'text-gray-600 bg-gray-50')}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-gray-900">{d.employe_nom}</p>
                        <span className="text-xs text-gray-400">{d.date_demande}</span>
                      </div>
                      <p className="text-sm text-gray-700 mt-0.5">{d.description}</p>
                      {(d.date_debut || d.date_fin) && (
                        <p className="text-xs text-gray-400 mt-0.5">{d.date_debut} → {d.date_fin}</p>
                      )}
                      {/* Chaîne hiérarchique */}
                      <div className="flex items-center gap-1.5 mt-2 text-xs text-gray-400">
                        <CheckCircleIcon className="h-3.5 w-3.5 text-green-500" />
                        <span className="text-green-600">Validé par hiérarchie</span>
                        <span>→</span>
                        <ClockIcon className="h-3.5 w-3.5 text-amber-500" />
                        <span>En attente RH</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => setSelected(d)}
                      className="flex-1 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-xs font-medium hover:bg-gray-200">
                      Voir détail & commenter
                    </button>
                    <button onClick={() => { setSelected(d); valider('approuve') }}
                      className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700">
                      <CheckCircleIcon className="h-3.5 w-3.5" />Approuver
                    </button>
                    <button onClick={() => setSelected(d)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-xs font-medium hover:bg-red-200">
                      <XMarkIcon className="h-3.5 w-3.5" />Refuser
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {traitees.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Demandes traitées</p>
          <div className="space-y-2">
            {traitees.map(d => (
              <div key={d.id} className="bg-white border border-gray-200 rounded-xl p-3 flex items-center gap-3">
                <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium',
                  d.statut === 'approuve' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700')}>
                  {d.statut === 'approuve' ? 'Approuvé' : 'Refusé'}
                </span>
                <div className="flex-1">
                  <span className="text-sm font-medium text-gray-800">{d.employe_nom}</span>
                  <span className="text-xs text-gray-400 ml-2">{d.description}</span>
                </div>
                <span className="text-xs text-gray-400">{d.date_demande}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal commentaire/validation */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b">
              <h3 className="font-bold text-gray-900">Traiter la demande</h3>
              <button onClick={() => setSelected(null)}><XMarkIcon className="h-5 w-5" /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="bg-gray-50 rounded-xl p-3 text-sm">
                <p className="font-medium text-gray-800">{selected.employe_nom} · {selected.type}</p>
                <p className="text-gray-600 mt-1">{selected.description}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Commentaire RH (optionnel)</label>
                <textarea value={commentaire} onChange={e => setCommentaire(e.target.value)} rows={3}
                  placeholder="Motif, conditions, informations complémentaires…"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 outline-none resize-none" />
              </div>
            </div>
            <div className="p-5 border-t flex gap-3">
              <button onClick={() => valider('refuse')} disabled={traitant}
                className="flex-1 py-2 bg-red-50 text-red-700 border border-red-200 rounded-lg text-sm font-medium hover:bg-red-100 disabled:opacity-50">
                {traitant ? 'Traitement…' : 'Refuser'}
              </button>
              <button onClick={() => valider('approuve')} disabled={traitant}
                className="flex-1 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50">
                {traitant ? 'Traitement…' : 'Approuver'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Page principale ───────────────────────────────────────────────────────────

type OngletRH = 'registre' | 'documents' | 'demandes' | 'kpi' | 'archive' | 'rapports'
type ModeVue = 'employe' | 'rh'

export function RHPage() {
  const [modeVue, setModeVue] = useState<ModeVue>('rh')
  const [onglet, setOnglet] = useState<OngletRH>('registre')
  const enAttenteCount = DEMANDES_DEMO.filter(d => d.statut === 'en_attente').length

  const TABS = [
    { id: 'registre' as const,   label: 'Registre',   icon: UsersIcon },
    { id: 'documents' as const,  label: 'Documents',  icon: DocumentTextIcon },
    { id: 'demandes' as const,   label: 'Validation demandes', icon: ClipboardDocumentCheckIcon, badge: enAttenteCount },
    { id: 'kpi' as const,        label: 'KPI Perf.',  icon: ChartBarIcon },
    { id: 'archive' as const,    label: 'Archive',    icon: FolderOpenIcon },
    { id: 'rapports' as const,   label: 'Rapports',   icon: DocumentTextIcon },
  ]

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header + sélecteur de vue */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ressources Humaines</h1>
          <p className="text-sm text-gray-500 mt-1">
            {modeVue === 'employe' ? 'Mon espace personnel — demandes & documents' : 'Tableau de bord RH · Gestion complète du personnel'}
          </p>
          <DemoBanner className="mt-2" />
        </div>
        {/* Sélecteur de vue — en prod : basé sur le rôle JWT */}
        <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-xl">
          <button onClick={() => setModeVue('employe')}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              modeVue === 'employe' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
            <UserIcon className="h-4 w-4" />Vue Employé
          </button>
          <button onClick={() => setModeVue('rh')}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              modeVue === 'rh' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
            <UsersIcon className="h-4 w-4" />Service RH
          </button>
        </div>
      </div>

      {/* Vue Employé — accès restreint */}
      {modeVue === 'employe' && <PortailEmploye />}

      {/* Vue RH Service — accès complet */}
      {modeVue === 'rh' && (
        <>
          {/* Onglets */}
          <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit flex-wrap">
            {TABS.map(({ id, label, icon: Icon, badge }) => (
              <button key={id} onClick={() => setOnglet(id)}
                className={clsx('relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                  onglet === id ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                )}>
                <Icon className="h-4 w-4" />
                {label}
                {badge && badge > 0 && (
                  <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-xs w-4 h-4 rounded-full flex items-center justify-center font-bold">
                    {badge}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Contenu */}
          {onglet === 'registre'   && <OngletRegistre />}
          {onglet === 'documents'  && <OngletDocuments />}
          {onglet === 'demandes'   && <OngletValidationDemandes />}
          {onglet === 'kpi'        && <OngletKPI />}
          {onglet === 'archive'    && (
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h3 className="text-base font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <FolderOpenIcon className="h-5 w-5 text-primary-600" />
                Archive numérique — RH
              </h3>
              <ArchiveNumerique module="rh" hauteurMax="500px" />
            </div>
          )}
          {onglet === 'rapports' && (
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <RapportsModule module="rh" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
