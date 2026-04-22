import { useState, useRef, useCallback } from 'react'
import {
  CloudArrowUpIcon, DocumentTextIcon, CheckCircleIcon, ClockIcon,
  ExclamationTriangleIcon, EyeIcon, ArrowPathIcon, SparklesIcon,
  XMarkIcon, BuildingStorefrontIcon, CameraIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { apiClient } from '../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

interface PieceFournisseur {
  id: string; fournisseur: string; type_fournisseur: string
  sinistre_ref: string; type_document: string
  fichier_nom: string; date_envoi: string
  statut: 'en_attente' | 'en_analyse' | 'valide' | 'rejete'
  score_ia?: number; analyse_ia?: string; importer_orass?: boolean
}

const TYPES_FOURNISSEUR = [
  { value: 'garage', label: 'Garage / Carrosserie', icon: '🔧' },
  { value: 'clinique', label: 'Clinique / Hôpital', icon: '🏥' },
  { value: 'pharmacie', label: 'Pharmacie', icon: '💊' },
  { value: 'expert', label: 'Expert / Expertise', icon: '🔍' },
  { value: 'avocat', label: 'Avocat / Huissier', icon: '⚖️' },
  { value: 'pompes_funebres', label: 'Pompes funèbres', icon: '🕊️' },
  { value: 'autre', label: 'Autre prestataire', icon: '📋' },
]

const TYPES_DOCUMENT = [
  'Facture de réparation', 'Devis de réparation', 'Facture médicale',
  'Facture hospitalisation', 'Ordonnance médicale', 'Certificat médical',
  'Rapport d\'expertise', 'Facture de funérailles', 'Facture de tiers',
  'Bon de commande', 'Reçu de paiement',
]

const DEMO_PIECES: PieceFournisseur[] = [
  {
    id: '1', fournisseur: 'Garage Toyota Douala', type_fournisseur: 'garage',
    sinistre_ref: 'SIN-2026-001', type_document: 'Facture de réparation',
    fichier_nom: 'facture_reparation_2026_0234.pdf', date_envoi: '2026-04-08T09:30:00',
    statut: 'en_analyse', score_ia: 88,
    analyse_ia: 'Facture conforme — montant cohérent avec le devis initial (2 480 000 XAF). Aucune anomalie détectée. Recommandation : valider et importer dans ORASS.',
  },
  {
    id: '2', fournisseur: 'Clinique Saint-Luc Yaoundé', type_fournisseur: 'clinique',
    sinistre_ref: 'SIN-2026-003', type_document: 'Facture hospitalisation',
    fichier_nom: 'facture_hospit_marc.pdf', date_envoi: '2026-04-07T14:15:00',
    statut: 'valide', score_ia: 95, importer_orass: true,
    analyse_ia: 'Document authentique — durée séjour cohérente avec contrat. Remboursable : 720 000 XAF.',
  },
  {
    id: '3', fournisseur: 'Garage Maxi-Auto', type_fournisseur: 'garage',
    sinistre_ref: 'SIN-2026-004', type_document: 'Facture de réparation',
    fichier_nom: 'facture_garage_seydou.pdf', date_envoi: '2026-04-09T11:00:00',
    statut: 'rejete', score_ia: 23,
    analyse_ia: '⚠️ ANOMALIE DÉTECTÉE : Montant facturé (12 000 000 XAF) incohérent avec le devis (3 200 000 XAF). Numéro de facture suspect (modifié numériquement). Risque fraude élevé — ne pas importer.',
  },
  {
    id: '4', fournisseur: 'Dr. Anouman Cabinet Médical', type_fournisseur: 'clinique',
    sinistre_ref: 'SIN-2026-005', type_document: 'Rapport d\'expertise',
    fichier_nom: 'rapport_expertise_ipp.pdf', date_envoi: '2026-04-09T16:45:00',
    statut: 'en_attente',
  },
]

// ─── Composant Upload Document ─────────────────────────────────────────────────

interface UploadFormState {
  fournisseur: string; type_fournisseur: string; sinistre_ref: string; type_document: string
}

function PortailFournisseur({ onEnvoi }: { onEnvoi: (p: PieceFournisseur) => void }) {
  const [form, setForm] = useState<UploadFormState>({
    fournisseur: '', type_fournisseur: 'garage', sinistre_ref: '', type_document: TYPES_DOCUMENT[0],
  })
  const [fichier, setFichier] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [succes, setSucces] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File) => {
    setFichier(f)
    if (f.type.startsWith('image/')) {
      const url = URL.createObjectURL(f)
      setPreview(url)
    } else {
      setPreview(null)
    }
  }, [])

  const soumettre = async () => {
    if (!fichier || !form.fournisseur || !form.sinistre_ref) return
    setLoading(true)
    await new Promise(r => setTimeout(r, 1200))
    const p: PieceFournisseur = {
      id: Date.now().toString(),
      fournisseur: form.fournisseur,
      type_fournisseur: form.type_fournisseur,
      sinistre_ref: form.sinistre_ref,
      type_document: form.type_document,
      fichier_nom: fichier.name,
      date_envoi: new Date().toISOString(),
      statut: 'en_attente',
    }
    onEnvoi(p)
    setLoading(false)
    setSucces(true)
    setFichier(null)
    setPreview(null)
  }

  if (succes) {
    return (
      <div className="text-center py-8 space-y-4">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
          <CheckCircleIcon className="h-10 w-10 text-green-600" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900">Document envoyé avec succès</h3>
        <p className="text-sm text-gray-500">La compagnie d'assurance a reçu votre document. Yukpo IA va l'analyser automatiquement.</p>
        <button onClick={() => setSucces(false)}
          className="bg-primary-600 text-white px-6 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700">
          Envoyer un autre document
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-800">
        <p className="font-semibold mb-1">Portail fournisseur sécurisé</p>
        <p className="text-xs">Vos documents sont transmis directement au gestionnaire du dossier. Yukpo IA analyse automatiquement chaque pièce avant validation humaine.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Votre raison sociale *</label>
          <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Garage Central Douala…" value={form.fournisseur}
            onChange={e => setForm(p => ({ ...p, fournisseur: e.target.value }))} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type de fournisseur</label>
          <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={form.type_fournisseur} onChange={e => setForm(p => ({ ...p, type_fournisseur: e.target.value }))}>
            {TYPES_FOURNISSEUR.map(t => <option key={t.value} value={t.value}>{t.icon} {t.label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Référence sinistre *</label>
          <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
            placeholder="SIN-2026-XXX" value={form.sinistre_ref}
            onChange={e => setForm(p => ({ ...p, sinistre_ref: e.target.value }))} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type de document</label>
          <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={form.type_document} onChange={e => setForm(p => ({ ...p, type_document: e.target.value }))}>
            {TYPES_DOCUMENT.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Document à transmettre *</label>
        <div
          className={clsx('border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
            dragOver ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
          )}
          onClick={() => inputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); e.dataTransfer.files[0] && handleFile(e.dataTransfer.files[0]) }}
        >
          {preview ? (
            <div className="space-y-2">
              <img src={preview} alt="Preview" className="max-h-40 mx-auto rounded-lg object-contain" />
              <p className="text-sm text-gray-600">{fichier?.name}</p>
              <p className="text-xs text-gray-400">{fichier && (fichier.size / 1024).toFixed(0)} Ko</p>
            </div>
          ) : fichier ? (
            <div className="space-y-2">
              <DocumentTextIcon className="h-10 w-10 text-primary-500 mx-auto" />
              <p className="text-sm font-medium text-gray-700">{fichier.name}</p>
              <p className="text-xs text-gray-400">{(fichier.size / 1024).toFixed(0)} Ko</p>
            </div>
          ) : (
            <>
              <CloudArrowUpIcon className="h-10 w-10 text-gray-400 mx-auto mb-2" />
              <p className="text-sm font-medium text-gray-700">Glissez votre document ici ou cliquez pour sélectionner</p>
              <p className="text-xs text-gray-400 mt-1">PDF, JPG, PNG — max 20 Mo</p>
            </>
          )}
          <input ref={inputRef} type="file" className="hidden" accept="image/*,.pdf"
            onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
        </div>
        <button type="button"
          className="mt-2 w-full flex items-center justify-center gap-2 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
          onClick={() => { if (inputRef.current) { inputRef.current.accept = 'image/*'; inputRef.current.capture = 'environment'; inputRef.current.click() } }}>
          <CameraIcon className="h-4 w-4" /> Utiliser l'appareil photo
        </button>
      </div>

      <button onClick={soumettre} disabled={!fichier || !form.fournisseur || !form.sinistre_ref || loading}
        className="w-full flex items-center justify-center gap-2 bg-primary-600 text-white py-3 rounded-xl text-sm font-semibold hover:bg-primary-700 disabled:opacity-50 transition-colors">
        {loading ? <><ArrowPathIcon className="h-4 w-4 animate-spin" /> Envoi en cours…</> : <><CloudArrowUpIcon className="h-4 w-4" /> Transmettre le document</>}
      </button>
    </div>
  )
}

// ─── File d'attente employé ────────────────────────────────────────────────────

function FileAttente({ pieces, onUpdate }: { pieces: PieceFournisseur[]; onUpdate: (p: PieceFournisseur) => void }) {
  const [selected, setSelected] = useState<PieceFournisseur | null>(null)
  const [analysing, setAnalysing] = useState<string | null>(null)

  const lancerAnalyse = async (p: PieceFournisseur) => {
    setAnalysing(p.id)
    onUpdate({ ...p, statut: 'en_analyse' })
    await new Promise(r => setTimeout(r, 2000))
    const score = Math.floor(Math.random() * 40) + 55
    const analyse = score > 80
      ? `Document conforme — montant cohérent avec le dossier sinistre ${p.sinistre_ref}. Aucune anomalie. Recommandation : valider et importer dans ORASS.`
      : score > 60
      ? `Document probablement valide — vérification manuelle recommandée avant import ORASS.`
      : `⚠️ ANOMALIE DÉTECTÉE : incohérence dans les montants ou dates. Risque fraude moyen. Ne pas importer sans vérification approfondie.`
    onUpdate({ ...p, statut: 'en_analyse', score_ia: score, analyse_ia: analyse })
    setAnalysing(null)
  }

  const valider = (p: PieceFournisseur) => onUpdate({ ...p, statut: 'valide', importer_orass: true })
  const rejeter = (p: PieceFournisseur) => onUpdate({ ...p, statut: 'rejete', importer_orass: false })

  const STATUT_CFG: Record<string, { label: string; icon: React.ReactNode; classes: string }> = {
    en_attente: { label: 'En attente', icon: <ClockIcon className="h-3.5 w-3.5" />, classes: 'bg-gray-100 text-gray-600' },
    en_analyse: { label: 'Analyse IA', icon: <SparklesIcon className="h-3.5 w-3.5" />, classes: 'bg-blue-100 text-blue-700' },
    valide: { label: 'Validé', icon: <CheckCircleIcon className="h-3.5 w-3.5" />, classes: 'bg-green-100 text-green-700' },
    rejete: { label: 'Rejeté', icon: <ExclamationTriangleIcon className="h-3.5 w-3.5" />, classes: 'bg-red-100 text-red-700' },
  }

  const enAttente = pieces.filter(p => p.statut === 'en_attente').length

  return (
    <div className="space-y-4">
      {enAttente > 0 && (
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-700">
          <ClockIcon className="h-4 w-4 flex-shrink-0" />
          <span><strong>{enAttente}</strong> pièce(s) en attente d'analyse — vérifiez la file avant validation ORASS</span>
        </div>
      )}

      <div className="space-y-2">
        {pieces.map(p => {
          const cfg = STATUT_CFG[p.statut]
          const typFrn = TYPES_FOURNISSEUR.find(t => t.value === p.type_fournisseur)
          return (
            <div key={p.id} className={clsx('bg-white border rounded-xl p-4',
              p.statut === 'rejete' ? 'border-red-200' : p.statut === 'valide' ? 'border-green-200' : 'border-gray-200')}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="text-2xl flex-shrink-0">{typFrn?.icon || '📄'}</div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-900 truncate">{p.fournisseur}</p>
                    <p className="text-xs text-gray-500">{p.type_document} · {p.sinistre_ref}</p>
                    <p className="text-xs text-gray-400 truncate">{p.fichier_nom}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {p.score_ia != null && (
                    <span className={clsx('text-xs font-bold px-2 py-0.5 rounded-full',
                      p.score_ia > 80 ? 'bg-green-100 text-green-700' : p.score_ia > 60 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700')}>
                      IA {p.score_ia}%
                    </span>
                  )}
                  <span className={clsx('flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full', cfg.classes)}>
                    {cfg.icon}{cfg.label}
                  </span>
                </div>
              </div>

              {p.analyse_ia && (
                <div className={clsx('mt-3 text-xs rounded-lg p-2.5',
                  (p.score_ia || 0) > 80 ? 'bg-green-50 text-green-800' : (p.score_ia || 0) > 60 ? 'bg-yellow-50 text-yellow-800' : 'bg-red-50 text-red-800')}>
                  <span className="font-semibold">Yukpo IA : </span>{p.analyse_ia}
                </div>
              )}

              <div className="flex gap-2 mt-3">
                {p.statut === 'en_attente' && (
                  <button onClick={() => lancerAnalyse(p)} disabled={analysing === p.id}
                    className="flex items-center gap-1 text-xs bg-primary-600 text-white px-3 py-1.5 rounded-lg hover:bg-primary-700 disabled:opacity-60">
                    {analysing === p.id ? <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" /> : <SparklesIcon className="h-3.5 w-3.5" />}
                    Analyser
                  </button>
                )}
                {p.statut === 'en_analyse' && !p.analyse_ia && (
                  <span className="text-xs text-blue-600 flex items-center gap-1">
                    <ArrowPathIcon className="h-3 w-3 animate-spin" /> Analyse en cours…
                  </span>
                )}
                {(p.statut === 'en_analyse' && p.analyse_ia) && (
                  <>
                    <button onClick={() => valider(p)}
                      className="flex items-center gap-1 text-xs bg-green-600 text-white px-3 py-1.5 rounded-lg hover:bg-green-700">
                      <CheckCircleIcon className="h-3.5 w-3.5" /> Valider → ORASS
                    </button>
                    <button onClick={() => rejeter(p)}
                      className="flex items-center gap-1 text-xs border border-red-300 text-red-600 px-3 py-1.5 rounded-lg hover:bg-red-50">
                      <XMarkIcon className="h-3.5 w-3.5" /> Rejeter
                    </button>
                  </>
                )}
                {p.statut === 'valide' && (
                  <span className="text-xs text-green-600 flex items-center gap-1 font-medium">
                    <CheckCircleIcon className="h-3.5 w-3.5" /> Importé dans ORASS/Mercure
                  </span>
                )}
                <button onClick={() => setSelected(selected?.id === p.id ? null : p)}
                  className="flex items-center gap-1 text-xs text-gray-500 px-2 py-1.5 rounded-lg hover:bg-gray-100 ml-auto">
                  <EyeIcon className="h-3.5 w-3.5" /> Détail
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {pieces.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <DocumentTextIcon className="h-10 w-10 mx-auto mb-2" />
          <p className="text-sm">Aucune pièce en attente</p>
        </div>
      )}
    </div>
  )
}

// ─── Page principale ──────────────────────────────────────────────────────────

type OngletFournisseur = 'portail' | 'file_attente'

export default function FournisseurPage() {
  const [onglet, setOnglet] = useState<OngletFournisseur>('file_attente')
  const [pieces, setPieces] = useState<PieceFournisseur[]>(DEMO_PIECES)

  const ajouterPiece = (p: PieceFournisseur) => {
    setPieces(prev => [p, ...prev])
    setOnglet('file_attente')
  }

  const updatePiece = (p: PieceFournisseur) =>
    setPieces(prev => prev.map(pp => pp.id === p.id ? p : pp))

  const enAttente = pieces.filter(p => p.statut === 'en_attente').length

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Portail Fournisseurs</h1>
          <p className="text-sm text-gray-500 mt-0.5">Réception des pièces · Analyse IA · Validation ORASS/Mercure</p>
        </div>
        <div className="flex items-center gap-2 text-xs bg-amber-50 text-amber-700 px-3 py-1.5 rounded-full border border-amber-200">
          <ClockIcon className="h-3.5 w-3.5" />
          {enAttente} pièce(s) en attente
        </div>
      </div>

      {/* Onglets */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        <button onClick={() => setOnglet('file_attente')}
          className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all relative',
            onglet === 'file_attente' ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
          <DocumentTextIcon className="h-4 w-4" />
          File d'attente employé
          {enAttente > 0 && <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-xs w-4 h-4 rounded-full flex items-center justify-center">{enAttente}</span>}
        </button>
        <button onClick={() => setOnglet('portail')}
          className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
            onglet === 'portail' ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
          <BuildingStorefrontIcon className="h-4 w-4" />
          Portail fournisseur
        </button>
      </div>

      {onglet === 'portail' && (
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <PortailFournisseur onEnvoi={ajouterPiece} />
        </div>
      )}

      {onglet === 'file_attente' && (
        <FileAttente pieces={pieces} onUpdate={updatePiece} />
      )}
    </div>
  )
}
