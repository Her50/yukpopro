/**
 * ArchiveNumerique — Composant d'archivage numérique transversal
 * Accessible depuis tous les modules. Filtre les documents par module/contexte.
 * Permet upload, recherche, prévisualisation et téléchargement.
 */
import { useState, useCallback, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  FolderOpenIcon, MagnifyingGlassIcon, ArrowDownTrayIcon,
  DocumentTextIcon, PhotoIcon, DocumentArrowUpIcon,
  FunnelIcon, EyeIcon, ClockIcon, CheckCircleIcon,
  XMarkIcon, TagIcon, BuildingStorefrontIcon,
  ShieldExclamationIcon, CurrencyDollarIcon, UsersIcon,
  ShieldCheckIcon, ClipboardDocumentCheckIcon, ChartBarIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import axios from 'axios'

// ─── Types ─────────────────────────────────────────────────────────────────────

export type ModuleArchive =
  | 'sinistres' | 'souscription' | 'comptabilite' | 'rh'
  | 'reassurance' | 'commercial' | 'fournisseurs' | 'tous'

interface DocumentArchive {
  id: string
  nom: string
  type_document: string
  module: ModuleArchive
  reference: string          // N° sinistre, N° police, N° contrat…
  date_upload: string
  taille_ko: number
  uploade_par: string
  tags: string[]
  url_preview?: string
  statut_ocr: 'non_traite' | 'en_cours' | 'extrait' | 'importe_orass'
  confiance_ocr?: number
  miniature?: string         // base64 ou URL
}

interface ArchiveNumeriqueProps {
  module?: ModuleArchive     // filtre par défaut
  referenceContexte?: string // n° sinistre ou police pré-filtré
  hauteurMax?: string
  showUpload?: boolean
}

// ─── Config modules ────────────────────────────────────────────────────────────

const MODULES_CONFIG: Record<ModuleArchive, { label: string; couleur: string; icon: React.ComponentType<{ className?: string }> }> = {
  sinistres:      { label: 'Sinistres',        couleur: 'text-red-600 bg-red-50',      icon: ShieldExclamationIcon },
  souscription:   { label: 'Souscription',     couleur: 'text-blue-600 bg-blue-50',    icon: ClipboardDocumentCheckIcon },
  comptabilite:   { label: 'Comptabilité',     couleur: 'text-amber-600 bg-amber-50',  icon: CurrencyDollarIcon },
  rh:             { label: 'RH',               couleur: 'text-purple-600 bg-purple-50',icon: UsersIcon },
  reassurance:    { label: 'Réassurance',      couleur: 'text-teal-600 bg-teal-50',    icon: ShieldCheckIcon },
  commercial:     { label: 'Commercial',       couleur: 'text-green-600 bg-green-50',  icon: ChartBarIcon },
  fournisseurs:   { label: 'Fournisseurs',     couleur: 'text-indigo-600 bg-indigo-50',icon: BuildingStorefrontIcon },
  tous:           { label: 'Tous modules',     couleur: 'text-gray-600 bg-gray-50',    icon: FolderOpenIcon },
}

const TYPES_DOC = [
  'Tous', 'Facture', 'Contrat', 'Rapport', 'Attestation', 'CNI/Passeport',
  'Carte grise', 'Constat', 'Bulletin de paie', 'Traité réassurance', 'Bordereau',
  'Formulaire', 'Correspondance', 'Photo', 'Autre',
]

// ─── Démo data ─────────────────────────────────────────────────────────────────

const DOCS_DEMO: DocumentArchive[] = [
  {
    id: 'd1', nom: 'constat_amiable_SIN-342.pdf', type_document: 'Constat',
    module: 'sinistres', reference: 'SIN-2026-0342', date_upload: '2026-04-08 14:32',
    taille_ko: 245, uploade_par: 'Traore F.', tags: ['auto', 'B10'],
    statut_ocr: 'importe_orass', confiance_ocr: 0.94,
  },
  {
    id: 'd2', nom: 'facture_clinique_SIN-289.pdf', type_document: 'Facture',
    module: 'sinistres', reference: 'SIN-2026-0289', date_upload: '2026-04-07 09:15',
    taille_ko: 312, uploade_par: 'Garage Central', tags: ['vie', 'B80', 'fournisseur'],
    statut_ocr: 'extrait', confiance_ocr: 0.91,
  },
  {
    id: 'd3', nom: 'police_auto_COMT-1892.pdf', type_document: 'Contrat',
    module: 'souscription', reference: 'COMT-2026-1892', date_upload: '2026-04-05 11:20',
    taille_ko: 158, uploade_par: 'Bamba A.', tags: ['auto', 'B10', 'police'],
    statut_ocr: 'importe_orass', confiance_ocr: 0.97,
  },
  {
    id: 'd4', nom: 'bulletin_paie_EMP001_mars.pdf', type_document: 'Bulletin de paie',
    module: 'rh', reference: 'EMP-001', date_upload: '2026-04-01 08:00',
    taille_ko: 89, uploade_par: 'N\'Goran MC.', tags: ['rh', 'paie', 'mars2026'],
    statut_ocr: 'extrait', confiance_ocr: 0.99,
  },
  {
    id: 'd5', nom: 'traite_quoteparte_SCOR_2026.pdf', type_document: 'Traité réassurance',
    module: 'reassurance', reference: 'TRAITE-SCOR-2026', date_upload: '2026-01-15 10:00',
    taille_ko: 2840, uploade_par: 'Kouassi JB.', tags: ['réassurance', 'SCOR', '2026'],
    statut_ocr: 'importe_orass', confiance_ocr: 0.88,
  },
  {
    id: 'd6', nom: 'facture_fournisseur_garage_342.pdf', type_document: 'Facture',
    module: 'fournisseurs', reference: 'SIN-2026-0342', date_upload: '2026-04-09 16:45',
    taille_ko: 195, uploade_par: 'Garage Central YDE', tags: ['garage', 'fournisseur'],
    statut_ocr: 'en_cours',
  },
  {
    id: 'd7', nom: 'devis_reparation_SIN-301.pdf', type_document: 'Rapport',
    module: 'sinistres', reference: 'SIN-2026-0301', date_upload: '2026-04-06 16:45',
    taille_ko: 420, uploade_par: 'Expert SARL', tags: ['expertise', 'auto'],
    statut_ocr: 'non_traite',
  },
  {
    id: 'd8', nom: 'bordereau_cession_Q1_2026.xlsx', type_document: 'Bordereau',
    module: 'reassurance', reference: 'BORD-Q1-2026', date_upload: '2026-04-02 14:20',
    taille_ko: 78, uploade_par: 'Diallo I.', tags: ['bordereau', 'cession', 'Q1'],
    statut_ocr: 'extrait', confiance_ocr: 0.95,
  },
  {
    id: 'd9', nom: 'cni_assuré_COMT-1950.jpg', type_document: 'CNI/Passeport',
    module: 'souscription', reference: 'COMT-2026-1950', date_upload: '2026-04-03 15:10',
    taille_ko: 520, uploade_par: 'Bamba A.', tags: ['cni', 'identité'],
    statut_ocr: 'importe_orass', confiance_ocr: 0.96,
  },
  {
    id: 'd10', nom: 'contrat_travail_EMP-005.pdf', type_document: 'Contrat',
    module: 'rh', reference: 'EMP-005', date_upload: '2022-09-01 09:00',
    taille_ko: 340, uploade_par: 'N\'Goran MC.', tags: ['rh', 'contrat', 'cdi'],
    statut_ocr: 'importe_orass', confiance_ocr: 0.98,
  },
]

// ─── Statut OCR badge ──────────────────────────────────────────────────────────

function OcrBadge({ statut, confiance }: { statut: DocumentArchive['statut_ocr']; confiance?: number }) {
  const cfg = {
    non_traite:     { label: 'Non traité', cls: 'bg-gray-100 text-gray-600' },
    en_cours:       { label: 'OCR en cours…', cls: 'bg-amber-100 text-amber-700' },
    extrait:        { label: `Extrait ${confiance ? Math.round(confiance * 100) + '%' : ''}`, cls: 'bg-blue-100 text-blue-700' },
    importe_orass:  { label: 'Importé ORASS', cls: 'bg-green-100 text-green-700' },
  }[statut]
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium', cfg.cls)}>
      {statut === 'importe_orass' && <CheckCircleIcon className="h-3 w-3" />}
      {statut === 'en_cours' && <ClockIcon className="h-3 w-3 animate-spin" />}
      {cfg.label}
    </span>
  )
}

// ─── Carte document ────────────────────────────────────────────────────────────

function CarteDocument({ doc, onPreview }: { doc: DocumentArchive; onPreview: (d: DocumentArchive) => void }) {
  const modCfg = MODULES_CONFIG[doc.module]
  const Icon = modCfg.icon
  const ext = doc.nom.split('.').pop()?.toUpperCase() ?? 'DOC'
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext.toLowerCase())

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow group">
      <div className="flex items-start gap-3">
        {/* Icône type */}
        <div className={clsx('w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0', modCfg.couleur)}>
          {isImage ? <PhotoIcon className="h-5 w-5" /> : <DocumentTextIcon className="h-5 w-5" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{doc.nom}</p>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={clsx('text-xs font-medium px-1.5 py-0.5 rounded', modCfg.couleur)}>
              <Icon className="h-3 w-3 inline mr-1" />{modCfg.label}
            </span>
            <span className="text-xs text-gray-500 font-mono">{doc.reference}</span>
          </div>
        </div>
        {/* Actions */}
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onPreview(doc)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-primary-600 hover:bg-primary-50 transition-colors"
            title="Prévisualiser"
          >
            <EyeIcon className="h-4 w-4" />
          </button>
          <a
            href={doc.url_preview ?? '#'}
            download={doc.nom}
            className="p-1.5 rounded-lg text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
            title="Télécharger"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
          </a>
        </div>
      </div>

      {/* Méta + OCR */}
      <div className="mt-3 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span><ClockIcon className="h-3 w-3 inline mr-1" />{doc.date_upload}</span>
          <span>{doc.taille_ko < 1000 ? `${doc.taille_ko} Ko` : `${(doc.taille_ko / 1024).toFixed(1)} Mo`}</span>
          <span>{doc.uploade_par}</span>
        </div>
        <OcrBadge statut={doc.statut_ocr} confiance={doc.confiance_ocr} />
      </div>

      {/* Tags */}
      {doc.tags.length > 0 && (
        <div className="mt-2 flex gap-1 flex-wrap">
          {doc.tags.map(t => (
            <span key={t} className="inline-flex items-center gap-0.5 bg-gray-100 text-gray-500 text-xs px-1.5 py-0.5 rounded">
              <TagIcon className="h-2.5 w-2.5" />{t}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Modal prévisualisation ────────────────────────────────────────────────────

function ModalPreview({ doc, onClose }: { doc: DocumentArchive | null; onClose: () => void }) {
  if (!doc) return null
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">{doc.nom}</h3>
            <p className="text-xs text-gray-500 mt-0.5">{doc.reference} · {doc.uploade_par}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
        <div className="p-6 overflow-y-auto" style={{ maxHeight: 'calc(90vh - 120px)' }}>
          {/* Prévisualisation simulée */}
          <div className="bg-gray-50 border border-gray-200 rounded-xl h-64 flex flex-col items-center justify-center gap-3">
            <DocumentTextIcon className="h-16 w-16 text-gray-300" />
            <p className="text-sm text-gray-500 font-medium">{doc.nom}</p>
            <p className="text-xs text-gray-400">
              {doc.taille_ko < 1000 ? `${doc.taille_ko} Ko` : `${(doc.taille_ko / 1024).toFixed(1)} Mo`}
            </p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {[
              ['Module', MODULES_CONFIG[doc.module].label],
              ['Référence', doc.reference],
              ['Type', doc.type_document],
              ['Uploadé par', doc.uploade_par],
              ['Date', doc.date_upload],
              ['Statut OCR', doc.statut_ocr.replace('_', ' ')],
            ].map(([k, v]) => (
              <div key={k} className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">{k}</p>
                <p className="font-medium text-gray-800">{v}</p>
              </div>
            ))}
          </div>
          {doc.confiance_ocr && (
            <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg flex items-center gap-2">
              <CheckCircleIcon className="h-4 w-4 text-green-600" />
              <span className="text-sm text-green-700 font-medium">
                OCR — confiance {Math.round(doc.confiance_ocr * 100)}%
              </span>
            </div>
          )}
          <div className="mt-4 flex gap-3">
            <button className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-primary-600 text-white rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors">
              <ArrowDownTrayIcon className="h-4 w-4" />
              Télécharger
            </button>
            {doc.statut_ocr !== 'importe_orass' && (
              <button className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700 transition-colors">
                <CheckCircleIcon className="h-4 w-4" />
                Importer dans ORASS
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Zone upload ───────────────────────────────────────────────────────────────

function ZoneUpload({ module, onUpload }: { module: ModuleArchive; onUpload: (d: DocumentArchive) => void }) {
  const [uploading, setUploading] = useState(false)
  const [reference, setReference] = useState('')
  const [typeDoc, setTypeDoc] = useState(TYPES_DOC[1])

  const onDrop = useCallback(async (files: File[]) => {
    if (!files.length) return
    setUploading(true)
    for (const file of files) {
      const nouveau: DocumentArchive = {
        id: Date.now().toString(),
        nom: file.name,
        type_document: typeDoc,
        module,
        reference: reference || 'REF-' + Date.now(),
        date_upload: new Date().toLocaleString('fr-FR'),
        taille_ko: Math.round(file.size / 1024),
        uploade_par: 'Moi',
        tags: [module],
        statut_ocr: 'en_cours',
      }
      onUpload(nouveau)
      try {
        const fd = new FormData()
        fd.append('fichier', file)
        fd.append('module', module)
        fd.append('reference', reference)
        fd.append('type_document', typeDoc)
        const res = await axios.post('/api/v1/archive/upload', fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        onUpload({ ...nouveau, ...(res.data as object), statut_ocr: 'extrait' })
      } catch {
        // Demo: simule OCR après 1.5s
        setTimeout(() => {
          onUpload({ ...nouveau, statut_ocr: 'extrait', confiance_ocr: 0.92 })
        }, 1500)
      }
    }
    setUploading(false)
  }, [module, reference, typeDoc, onUpload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, multiple: true })

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Référence (n° police, sinistre…)</label>
          <input
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            placeholder="SIN-2026-XXXX"
            value={reference}
            onChange={e => setReference(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type de document</label>
          <select
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            value={typeDoc}
            onChange={e => setTypeDoc(e.target.value)}
          >
            {TYPES_DOC.slice(1).map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>

      <div
        {...getRootProps()}
        className={clsx(
          'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
          isDragActive ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
        )}
      >
        <input {...getInputProps()} />
        {uploading ? (
          <div className="space-y-2">
            <div className="animate-spin h-8 w-8 border-2 border-primary-500 border-t-transparent rounded-full mx-auto" />
            <p className="text-sm text-gray-600">Upload et OCR en cours…</p>
          </div>
        ) : (
          <>
            <DocumentArrowUpIcon className="h-10 w-10 text-gray-400 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-700">Glissez vos documents ici ou cliquez</p>
            <p className="text-xs text-gray-400 mt-1">PDF, JPG, PNG, XLSX — max 50 Mo</p>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Composant principal ───────────────────────────────────────────────────────

export function ArchiveNumerique({
  module = 'tous',
  referenceContexte,
  hauteurMax = '600px',
  showUpload = true,
}: ArchiveNumeriqueProps) {
  const [docs, setDocs] = useState<DocumentArchive[]>(DOCS_DEMO)
  const [search, setSearch] = useState(referenceContexte ?? '')
  const [filtreModule, setFiltreModule] = useState<ModuleArchive>(module)
  const [filtreType, setFiltreType] = useState('Tous')
  const [filtreOcr, setFiltreOcr] = useState<string>('tous')
  const [preview, setPreview] = useState<DocumentArchive | null>(null)
  const [showUploadPanel, setShowUploadPanel] = useState(false)

  const docsFiltered = docs.filter(d => {
    const matchModule = filtreModule === 'tous' || d.module === filtreModule
    const matchType = filtreType === 'Tous' || d.type_document === filtreType
    const matchOcr = filtreOcr === 'tous' || d.statut_ocr === filtreOcr
    const q = search.toLowerCase()
    const matchSearch = !search || d.nom.toLowerCase().includes(q) || d.reference.toLowerCase().includes(q) || d.tags.join(' ').toLowerCase().includes(q)
    return matchModule && matchType && matchOcr && matchSearch
  })

  const ajouterDoc = useCallback((d: DocumentArchive) => {
    setDocs(prev => {
      const idx = prev.findIndex(x => x.id === d.id)
      return idx >= 0 ? prev.map(x => x.id === d.id ? d : x) : [d, ...prev]
    })
  }, [])

  const statsOcr = {
    total: docs.length,
    importe: docs.filter(d => d.statut_ocr === 'importe_orass').length,
    extrait: docs.filter(d => d.statut_ocr === 'extrait').length,
    enCours: docs.filter(d => d.statut_ocr === 'en_cours').length,
  }

  return (
    <div className="space-y-4">
      {/* En-tête avec stats */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5">
            <FolderOpenIcon className="h-4 w-4 text-primary-600" />
            <span className="font-semibold text-gray-900">{docsFiltered.length} document{docsFiltered.length > 1 ? 's' : ''}</span>
          </div>
          <span className="text-gray-400">|</span>
          <span className="text-green-600 font-medium">{statsOcr.importe} importés ORASS</span>
          <span className="text-blue-600 font-medium">{statsOcr.extrait} extraits</span>
          {statsOcr.enCours > 0 && <span className="text-amber-600 font-medium">{statsOcr.enCours} en cours</span>}
        </div>
        {showUpload && (
          <button
            onClick={() => setShowUploadPanel(!showUploadPanel)}
            className="flex items-center gap-2 bg-primary-600 text-white px-3 py-1.5 rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors"
          >
            <DocumentArrowUpIcon className="h-4 w-4" />
            {showUploadPanel ? 'Fermer' : 'Ajouter'}
          </button>
        )}
      </div>

      {/* Zone upload (toggle) */}
      {showUploadPanel && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
          <h4 className="text-sm font-semibold text-gray-700 mb-3">Ajouter un document</h4>
          <ZoneUpload module={filtreModule !== 'tous' ? filtreModule : module} onUpload={ajouterDoc} />
        </div>
      )}

      {/* Filtres */}
      <div className="flex gap-3 flex-wrap">
        {/* Recherche */}
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            placeholder="Rechercher par nom, référence, tag…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Filtre module */}
        {module === 'tous' && (
          <select
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            value={filtreModule}
            onChange={e => setFiltreModule(e.target.value as ModuleArchive)}
          >
            {(Object.keys(MODULES_CONFIG) as ModuleArchive[]).map(m => (
              <option key={m} value={m}>{MODULES_CONFIG[m].label}</option>
            ))}
          </select>
        )}

        {/* Filtre type */}
        <select
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          value={filtreType}
          onChange={e => setFiltreType(e.target.value)}
        >
          {TYPES_DOC.map(t => <option key={t}>{t}</option>)}
        </select>

        {/* Filtre OCR */}
        <select
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          value={filtreOcr}
          onChange={e => setFiltreOcr(e.target.value)}
        >
          <option value="tous">Tous statuts OCR</option>
          <option value="non_traite">Non traité</option>
          <option value="en_cours">En cours</option>
          <option value="extrait">Extrait</option>
          <option value="importe_orass">Importé ORASS</option>
        </select>
      </div>

      {/* Liste documents */}
      <div
        className="overflow-y-auto space-y-2 pr-1"
        style={{ maxHeight: hauteurMax }}
      >
        {docsFiltered.length === 0 ? (
          <div className="text-center py-16">
            <FolderOpenIcon className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-400 text-sm">Aucun document trouvé</p>
          </div>
        ) : (
          docsFiltered.map(doc => (
            <CarteDocument key={doc.id} doc={doc} onPreview={setPreview} />
          ))
        )}
      </div>

      {/* Modal prévisualisation */}
      {preview && <ModalPreview doc={preview} onClose={() => setPreview(null)} />}
    </div>
  )
}
