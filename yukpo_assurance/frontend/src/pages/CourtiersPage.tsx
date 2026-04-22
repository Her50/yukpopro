import { useState, useRef, useCallback, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts'
import {
  CloudArrowUpIcon, DocumentTextIcon, CheckCircleIcon, ClockIcon,
  ExclamationTriangleIcon, ArrowPathIcon, SparklesIcon, XMarkIcon,
  CameraIcon, BanknotesIcon, ChartBarIcon, DocumentCheckIcon,
  UserGroupIcon, InboxArrowDownIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { courtiersAPI } from '../api/client'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { KPICard } from '../components/KPICard'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DocumentCourtier {
  id: string
  courtier: string
  categorie: 'souscription' | 'sinistre' | 'comptabilite'
  reference: string
  type_document: string
  fichier_nom: string
  date_envoi: string
  statut: 'en_attente' | 'en_analyse' | 'valide' | 'rejete'
  score_ia?: number
  analyse_ia?: string
  importe_si?: boolean
}

interface Commission {
  id: string
  courtier: string
  periode: string
  branche: string
  primes: number
  taux: number
  montant: number
  statut: 'due' | 'payee' | 'en_litige'
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const DEMO_DASHBOARD = {
  production_mensuelle: 185_000_000,
  commissions_dues: 27_750_000,
  portefeuille_actif: 2340,
  top_produits: [
    { produit: 'Auto Tous Risques', primes: 72_000_000, contrats: 890 },
    { produit: 'MRH Multirisque', primes: 45_000_000, contrats: 620 },
    { produit: 'Vie Épargne', primes: 38_000_000, contrats: 380 },
    { produit: 'RC Entreprise', primes: 18_000_000, contrats: 210 },
    { produit: 'Santé Individuelle', primes: 12_000_000, contrats: 240 },
  ],
  evolution_production: [
    { mois: 'Août', production: 140_000_000, objectif: 160_000_000 },
    { mois: 'Sep', production: 158_000_000, objectif: 163_000_000 },
    { mois: 'Oct', production: 165_000_000, objectif: 165_000_000 },
    { mois: 'Nov', production: 170_000_000, objectif: 167_000_000 },
    { mois: 'Déc', production: 178_000_000, objectif: 168_000_000 },
    { mois: 'Jan', production: 185_000_000, objectif: 170_000_000 },
  ],
}

const DEMO_DOCUMENTS: DocumentCourtier[] = [
  {
    id: '1', courtier: 'Cabinet Assur-Plus Douala', categorie: 'souscription',
    reference: 'POL-2026-0412', type_document: 'Proposition d\'assurance',
    fichier_nom: 'proposition_auto_mballa.pdf', date_envoi: '2026-04-09T10:30:00',
    statut: 'en_analyse', score_ia: 92,
    analyse_ia: 'Document conforme — proposition bien renseignée pour l\'assuré Mballa Jean. Risque Auto standard. Recommandation : valider et enregistrer dans le SI.',
  },
  {
    id: '2', courtier: 'Intermédiaire SARL Transcam', categorie: 'sinistre',
    reference: 'SIN-2026-0234', type_document: 'Déclaration sinistre',
    fichier_nom: 'declaration_sinistre_fouda.pdf', date_envoi: '2026-04-08T14:20:00',
    statut: 'valide', score_ia: 87, importe_si: true,
    analyse_ia: 'Déclaration authentique — circonstances cohérentes. Dommages estimés à 2 800 000 XAF. Importé dans le dossier sinistre.',
  },
  {
    id: '3', courtier: 'Agence YK Courtage Yaoundé', categorie: 'comptabilite',
    reference: 'FACT-2026-0089', type_document: 'Bordereaux de primes',
    fichier_nom: 'bordereau_mars_2026.pdf', date_envoi: '2026-04-09T16:45:00',
    statut: 'rejete', score_ia: 28,
    analyse_ia: '⚠️ ANOMALIE : Montants du bordereau incohérents avec les encaissements enregistrés (écart de 1 400 000 XAF). Vérification manuelle requise avant tout import.',
  },
  {
    id: '4', courtier: 'Courtier Indépendant Ngando', categorie: 'souscription',
    reference: 'POL-2026-0415', type_document: 'Carte grise assurée',
    fichier_nom: 'cg_vehicule_ngando.jpg', date_envoi: '2026-04-10T08:00:00',
    statut: 'en_attente',
  },
]

const DEMO_COMMISSIONS: Commission[] = [
  { id: '1', courtier: 'Cabinet Assur-Plus Douala', periode: 'Mars 2026', branche: 'Auto', primes: 14_200_000, taux: 12, montant: 1_704_000, statut: 'due' },
  { id: '2', courtier: 'Intermédiaire SARL Transcam', periode: 'Mars 2026', branche: 'MRH', primes: 8_500_000, taux: 10, montant: 850_000, statut: 'payee' },
  { id: '3', courtier: 'Agence YK Courtage Yaoundé', periode: 'Fév 2026', branche: 'Vie', primes: 22_000_000, taux: 8, montant: 1_760_000, statut: 'en_litige' },
  { id: '4', courtier: 'Cabinet Assur-Plus Douala', periode: 'Fév 2026', branche: 'Santé', primes: 6_800_000, taux: 10, montant: 680_000, statut: 'payee' },
  { id: '5', courtier: 'Courtier Indépendant Ngando', periode: 'Mars 2026', branche: 'RC', primes: 3_200_000, taux: 15, montant: 480_000, statut: 'due' },
]

// ─── Utilitaires ──────────────────────────────────────────────────────────────

function fmt(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)} K`
  return `${v}`
}

const TYPES_DOCUMENT_PAR_CAT: Record<string, string[]> = {
  souscription: [
    'Proposition d\'assurance', 'Carte grise assurée', 'CNI assuré',
    'Devis / bordereau', 'Fiche client KYC', 'Attestation précédent assureur',
  ],
  sinistre: [
    'Déclaration sinistre', 'Constat amiable', 'Procès-verbal Police',
    'Rapport d\'expertise', 'Devis de réparation', 'Facture de réparation',
    'Certificat médical', 'Certificat de décès',
  ],
  comptabilite: [
    'Bordereaux de primes', 'Relevé de commissions', 'Facture honoraires',
    'Quittance de paiement', 'Avis de débit', 'Bordereau de reversement',
  ],
}

// ─── Onglet Tableau de bord ───────────────────────────────────────────────────

function OngletDashboard() {
  const [data, setData] = useState<typeof DEMO_DASHBOARD | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const result = await courtiersAPI.getTableauBord() as Record<string, unknown>
        setData((result?.production_mensuelle ? result : DEMO_DASHBOARD) as typeof DEMO_DASHBOARD)
      } catch {
        setData(DEMO_DASHBOARD)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return <div className="flex justify-center py-12"><LoadingSpinner size="lg" label="Chargement…" /></div>

  const d = data || DEMO_DASHBOARD
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KPICard title="Production mensuelle" value={fmt(d.production_mensuelle)}
          subtitle="FCFA — janvier 2025" icon={<BanknotesIcon className="h-6 w-6" />}
          trend={{ value: 9.2, label: 'vs jan 2024' }} color="blue" />
        <KPICard title="Commissions dues" value={fmt(d.commissions_dues)}
          subtitle="FCFA — à verser" icon={<ChartBarIcon className="h-6 w-6" />} color="green" />
        <KPICard title="Portefeuille actif" value={d.portefeuille_actif.toLocaleString('fr-FR')}
          subtitle="Polices en cours" icon={<DocumentCheckIcon className="h-6 w-6" />}
          trend={{ value: 5.8, label: 'vs jan 2024' }} color="purple" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Évolution de la production (FCFA)</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={d.evolution_production}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="mois" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={fmt} width={60} />
              <Tooltip formatter={(v: number) => [fmt(v), '']} contentStyle={{ borderRadius: '8px', fontSize: 12 }} />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="production" name="Réalisé" stroke="#0054A6" strokeWidth={2} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="objectif" name="Objectif" stroke="#00B0F0" strokeWidth={2} strokeDasharray="5 5" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Top produits</h3>
          <div className="space-y-3">
            {d.top_produits.map((p, i) => {
              const maxPrimes = d.top_produits[0].primes
              const pct = Math.round((p.primes / maxPrimes) * 100)
              return (
                <div key={p.produit}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="font-medium text-gray-700">{p.produit}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-500">{p.contrats} contrats</span>
                      <span className="font-semibold text-gray-900">{fmt(p.primes)} FCFA</span>
                    </div>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: ['#0054A6', '#00B0F0', '#10b981', '#f59e0b', '#8b5cf6'][i % 5] }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Portail Courtier (upload) ────────────────────────────────────────────────

function PortailCourtier({ onEnvoi }: { onEnvoi: (d: DocumentCourtier) => void }) {
  const [form, setForm] = useState({
    courtier: '', categorie: 'souscription' as DocumentCourtier['categorie'],
    reference: '', type_document: TYPES_DOCUMENT_PAR_CAT['souscription'][0],
  })
  const [fichier, setFichier] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [succes, setSucces] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((f: File) => {
    setFichier(f)
    setPreview(f.type.startsWith('image/') ? URL.createObjectURL(f) : null)
  }, [])

  const handleCategorieChange = (cat: DocumentCourtier['categorie']) => {
    setForm(p => ({ ...p, categorie: cat, type_document: TYPES_DOCUMENT_PAR_CAT[cat][0] }))
  }

  const soumettre = async () => {
    if (!fichier || !form.courtier || !form.reference) return
    setLoading(true)
    await new Promise(r => setTimeout(r, 1000))
    const doc: DocumentCourtier = {
      id: Date.now().toString(),
      courtier: form.courtier,
      categorie: form.categorie,
      reference: form.reference,
      type_document: form.type_document,
      fichier_nom: fichier.name,
      date_envoi: new Date().toISOString(),
      statut: 'en_attente',
    }
    onEnvoi(doc)
    setLoading(false)
    setSucces(true)
    setFichier(null)
    setPreview(null)
  }

  if (succes) {
    return (
      <div className="text-center py-10 space-y-4">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
          <CheckCircleIcon className="h-10 w-10 text-green-600" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900">Document transmis avec succès</h3>
        <p className="text-sm text-gray-500">La compagnie a reçu votre document. Yukpo IA va l'analyser automatiquement avant validation humaine.</p>
        <button onClick={() => setSucces(false)}
          className="bg-primary-600 text-white px-6 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700">
          Envoyer un autre document
        </button>
      </div>
    )
  }

  const typesDoc = TYPES_DOCUMENT_PAR_CAT[form.categorie]

  return (
    <div className="space-y-5">
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-800">
        <p className="font-semibold mb-1">Portail courtier sécurisé</p>
        <p className="text-xs">Transmettez vos documents scannés directement à la compagnie. Chaque pièce est analysée par Yukpo IA avant validation humaine et injection dans le SI.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Votre cabinet / raison sociale *</label>
          <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="Cabinet Assur-Plus Douala…" value={form.courtier}
            onChange={e => setForm(p => ({ ...p, courtier: e.target.value }))} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Catégorie du document *</label>
          <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={form.categorie} onChange={e => handleCategorieChange(e.target.value as DocumentCourtier['categorie'])}>
            <option value="souscription">📋 Souscription</option>
            <option value="sinistre">⚠️ Sinistre</option>
            <option value="comptabilite">💰 Comptabilité</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Référence dossier *</label>
          <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
            placeholder={form.categorie === 'sinistre' ? 'SIN-2026-XXX' : 'POL-2026-XXX'}
            value={form.reference}
            onChange={e => setForm(p => ({ ...p, reference: e.target.value }))} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Type de document</label>
          <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={form.type_document} onChange={e => setForm(p => ({ ...p, type_document: e.target.value }))}>
            {typesDoc.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-2">Document scanné *</label>
        <div
          className={clsx('border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
            dragOver ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50')}
          onClick={() => inputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); e.dataTransfer.files[0] && handleFile(e.dataTransfer.files[0]) }}
        >
          {preview ? (
            <div className="space-y-2">
              <img src={preview} alt="Preview" className="max-h-40 mx-auto rounded-lg object-contain" />
              <p className="text-sm text-gray-600">{fichier?.name}</p>
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
              <p className="text-sm font-medium text-gray-700">Glissez votre document ici ou cliquez</p>
              <p className="text-xs text-gray-400 mt-1">PDF, JPG, PNG — max 20 Mo</p>
            </>
          )}
          <input ref={inputRef} type="file" className="hidden" accept="image/*,.pdf"
            onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
        </div>
        <button type="button"
          className="mt-2 w-full flex items-center justify-center gap-2 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
          onClick={() => { if (inputRef.current) { inputRef.current.accept = 'image/*'; inputRef.current.capture = 'environment'; inputRef.current.click() } }}>
          <CameraIcon className="h-4 w-4" /> Utiliser l'appareil photo / scanner
        </button>
      </div>

      <button onClick={soumettre} disabled={!fichier || !form.courtier || !form.reference || loading}
        className="w-full flex items-center justify-center gap-2 bg-primary-600 text-white py-3 rounded-xl text-sm font-semibold hover:bg-primary-700 disabled:opacity-50 transition-colors">
        {loading ? <><ArrowPathIcon className="h-4 w-4 animate-spin" /> Envoi en cours…</> : <><CloudArrowUpIcon className="h-4 w-4" /> Transmettre à la compagnie</>}
      </button>
    </div>
  )
}

// ─── Documents reçus (OCR) ────────────────────────────────────────────────────

const STATUT_CFG: Record<string, { label: string; icon: React.ReactNode; classes: string }> = {
  en_attente: { label: 'En attente', icon: <ClockIcon className="h-3.5 w-3.5" />, classes: 'bg-gray-100 text-gray-600' },
  en_analyse: { label: 'Analyse IA', icon: <SparklesIcon className="h-3.5 w-3.5" />, classes: 'bg-blue-100 text-blue-700' },
  valide: { label: 'Validé', icon: <CheckCircleIcon className="h-3.5 w-3.5" />, classes: 'bg-green-100 text-green-700' },
  rejete: { label: 'Rejeté', icon: <ExclamationTriangleIcon className="h-3.5 w-3.5" />, classes: 'bg-red-100 text-red-700' },
}

const CAT_CFG: Record<string, { label: string; icon: string }> = {
  souscription: { label: 'Souscription', icon: '📋' },
  sinistre: { label: 'Sinistre', icon: '⚠️' },
  comptabilite: { label: 'Comptabilité', icon: '💰' },
}

function DocumentsRecus({
  documents, onUpdate, categorieFiltre,
}: {
  documents: DocumentCourtier[]
  onUpdate: (d: DocumentCourtier) => void
  categorieFiltre?: DocumentCourtier['categorie']
}) {
  const [analysing, setAnalysing] = useState<string | null>(null)
  const [filtreStatut, setFiltreStatut] = useState<string>('tous')

  const lancerAnalyse = async (d: DocumentCourtier) => {
    setAnalysing(d.id)
    onUpdate({ ...d, statut: 'en_analyse' })
    await new Promise(r => setTimeout(r, 2000))
    const score = Math.floor(Math.random() * 40) + 55
    const analyse = score > 80
      ? `Document conforme — données cohérentes avec le dossier ${d.reference}. Aucune anomalie détectée. Recommandation : valider et injecter dans le SI.`
      : score > 60
      ? `Document probablement valide — vérification manuelle recommandée avant import SI.`
      : `⚠️ ANOMALIE DÉTECTÉE : incohérence dans les montants ou données du document. Risque fraude moyen — ne pas importer sans vérification approfondie.`
    onUpdate({ ...d, statut: 'en_analyse', score_ia: score, analyse_ia: analyse })
    setAnalysing(null)
  }

  const valider = (d: DocumentCourtier) => onUpdate({ ...d, statut: 'valide', importe_si: true })
  const rejeter = (d: DocumentCourtier) => onUpdate({ ...d, statut: 'rejete' })

  let liste = categorieFiltre ? documents.filter(d => d.categorie === categorieFiltre) : documents
  if (filtreStatut !== 'tous') liste = liste.filter(d => d.statut === filtreStatut)

  const enAttente = (categorieFiltre ? documents.filter(d => d.categorie === categorieFiltre) : documents)
    .filter(d => d.statut === 'en_attente').length

  return (
    <div className="space-y-4">
      {enAttente > 0 && (
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-700">
          <ClockIcon className="h-4 w-4 flex-shrink-0" />
          <span><strong>{enAttente}</strong> document(s) courtier en attente d'analyse OCR</span>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {['tous', 'en_attente', 'en_analyse', 'valide', 'rejete'].map(s => (
          <button key={s} onClick={() => setFiltreStatut(s)}
            className={clsx('text-xs px-3 py-1 rounded-full border transition-colors',
              filtreStatut === s ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50')}>
            {s === 'tous' ? 'Tous' : STATUT_CFG[s]?.label ?? s}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {liste.map(d => {
          const cfg = STATUT_CFG[d.statut]
          const cat = CAT_CFG[d.categorie]
          return (
            <div key={d.id} className={clsx('bg-white border rounded-xl p-4',
              d.statut === 'rejete' ? 'border-red-200' : d.statut === 'valide' ? 'border-green-200' : 'border-gray-200')}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="text-2xl flex-shrink-0">{cat?.icon || '📄'}</div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-900 truncate">{d.courtier}</p>
                    <p className="text-xs text-gray-500">{d.type_document} · {d.reference}</p>
                    <p className="text-xs text-gray-400 truncate">{d.fichier_nom}</p>
                    <span className="text-xs text-gray-400 bg-gray-100 rounded px-1.5 py-0.5 mt-1 inline-block">
                      {cat?.label}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {d.score_ia != null && (
                    <span className={clsx('text-xs font-bold px-2 py-0.5 rounded-full',
                      d.score_ia > 80 ? 'bg-green-100 text-green-700' : d.score_ia > 60 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700')}>
                      IA {d.score_ia}%
                    </span>
                  )}
                  <span className={clsx('flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full', cfg.classes)}>
                    {cfg.icon}{cfg.label}
                  </span>
                </div>
              </div>

              {d.analyse_ia && (
                <div className={clsx('mt-3 text-xs rounded-lg p-2.5',
                  (d.score_ia || 0) > 80 ? 'bg-green-50 text-green-800' : (d.score_ia || 0) > 60 ? 'bg-yellow-50 text-yellow-800' : 'bg-red-50 text-red-800')}>
                  <span className="font-semibold">Yukpo IA : </span>{d.analyse_ia}
                </div>
              )}

              <div className="flex gap-2 mt-3 flex-wrap">
                {d.statut === 'en_attente' && (
                  <button onClick={() => lancerAnalyse(d)} disabled={analysing === d.id}
                    className="flex items-center gap-1 text-xs bg-primary-600 text-white px-3 py-1.5 rounded-lg hover:bg-primary-700 disabled:opacity-60">
                    {analysing === d.id ? <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" /> : <SparklesIcon className="h-3.5 w-3.5" />}
                    Analyser OCR
                  </button>
                )}
                {d.statut === 'en_analyse' && !d.analyse_ia && (
                  <span className="text-xs text-blue-600 flex items-center gap-1">
                    <ArrowPathIcon className="h-3 w-3 animate-spin" /> Analyse en cours…
                  </span>
                )}
                {d.statut === 'en_analyse' && d.analyse_ia && (
                  <>
                    <button onClick={() => valider(d)}
                      className="flex items-center gap-1 text-xs bg-green-600 text-white px-3 py-1.5 rounded-lg hover:bg-green-700">
                      <CheckCircleIcon className="h-3.5 w-3.5" /> Valider → SI
                    </button>
                    <button onClick={() => rejeter(d)}
                      className="flex items-center gap-1 text-xs border border-red-300 text-red-600 px-3 py-1.5 rounded-lg hover:bg-red-50">
                      <XMarkIcon className="h-3.5 w-3.5" /> Rejeter
                    </button>
                  </>
                )}
                {d.statut === 'valide' && (
                  <span className="text-xs text-green-600 flex items-center gap-1 font-medium">
                    <CheckCircleIcon className="h-3.5 w-3.5" /> Injecté dans le SI
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {liste.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <InboxArrowDownIcon className="h-10 w-10 mx-auto mb-2" />
          <p className="text-sm">Aucun document reçu</p>
        </div>
      )}
    </div>
  )
}

// ─── Onglet Commissions ───────────────────────────────────────────────────────

function OngletCommissions() {
  const [commissions] = useState<Commission[]>(DEMO_COMMISSIONS)
  const [filtreStatut, setFiltreStatut] = useState<string>('tous')

  const liste = filtreStatut === 'tous' ? commissions : commissions.filter(c => c.statut === filtreStatut)

  const totalDue = commissions.filter(c => c.statut === 'due').reduce((s, c) => s + c.montant, 0)
  const totalPayee = commissions.filter(c => c.statut === 'payee').reduce((s, c) => s + c.montant, 0)

  const STATUT_COMM: Record<string, { label: string; classes: string }> = {
    due: { label: 'Due', classes: 'bg-amber-100 text-amber-700' },
    payee: { label: 'Payée', classes: 'bg-green-100 text-green-700' },
    en_litige: { label: 'En litige', classes: 'bg-red-100 text-red-700' },
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-xs text-amber-600 font-medium">Commissions dues</p>
          <p className="text-xl font-bold text-amber-800 mt-1">{fmt(totalDue)} FCFA</p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <p className="text-xs text-green-600 font-medium">Commissions payées (période)</p>
          <p className="text-xl font-bold text-green-800 mt-1">{fmt(totalPayee)} FCFA</p>
        </div>
      </div>

      <div className="flex gap-2">
        {['tous', 'due', 'payee', 'en_litige'].map(s => (
          <button key={s} onClick={() => setFiltreStatut(s)}
            className={clsx('text-xs px-3 py-1 rounded-full border transition-colors',
              filtreStatut === s ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50')}>
            {s === 'tous' ? 'Toutes' : STATUT_COMM[s]?.label ?? s}
          </button>
        ))}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600">Courtier</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600">Période</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600">Branche</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600">Primes</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600">Taux</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-gray-600">Commission</th>
              <th className="text-center px-4 py-3 text-xs font-semibold text-gray-600">Statut</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {liste.map(c => {
              const scfg = STATUT_COMM[c.statut]
              return (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900 text-xs">{c.courtier}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{c.periode}</td>
                  <td className="px-4 py-3 text-gray-700 text-xs">{c.branche}</td>
                  <td className="px-4 py-3 text-right text-gray-700 text-xs font-mono">{fmt(c.primes)}</td>
                  <td className="px-4 py-3 text-right text-gray-700 text-xs">{c.taux}%</td>
                  <td className="px-4 py-3 text-right font-semibold text-gray-900 text-xs font-mono">{fmt(c.montant)}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', scfg.classes)}>{scfg.label}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {c.statut === 'due' && (
                      <button className="text-xs bg-green-600 text-white px-2 py-1 rounded-lg hover:bg-green-700">
                        Payer
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {liste.length === 0 && (
          <div className="text-center py-10 text-gray-400 text-sm">Aucune commission pour ce filtre</div>
        )}
      </div>
    </div>
  )
}

// ─── Page principale ──────────────────────────────────────────────────────────

type OngletCourtier = 'dashboard' | 'portail' | 'documents' | 'commissions'

export function CourtiersPage() {
  const [onglet, setOnglet] = useState<OngletCourtier>('dashboard')
  const [documents, setDocuments] = useState<DocumentCourtier[]>(DEMO_DOCUMENTS)

  const ajouterDocument = (d: DocumentCourtier) => {
    setDocuments(prev => [d, ...prev])
    setOnglet('documents')
  }

  const updateDocument = (d: DocumentCourtier) =>
    setDocuments(prev => prev.map(dd => dd.id === d.id ? d : dd))

  const enAttente = documents.filter(d => d.statut === 'en_attente').length

  const tabs: { key: OngletCourtier; label: string; icon: React.ReactNode }[] = [
    { key: 'dashboard', label: 'Tableau de bord', icon: <ChartBarIcon className="h-4 w-4" /> },
    { key: 'portail', label: 'Portail Courtier', icon: <UserGroupIcon className="h-4 w-4" /> },
    { key: 'documents', label: 'Documents reçus', icon: <InboxArrowDownIcon className="h-4 w-4" /> },
    { key: 'commissions', label: 'Commissions', icon: <BanknotesIcon className="h-4 w-4" /> },
  ]

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Courtiers & Intermédiaires</h2>
          <p className="text-sm text-gray-400">Production · Dématérialisation documents · Commissions</p>
        </div>
        {enAttente > 0 && (
          <div className="flex items-center gap-2 text-xs bg-amber-50 text-amber-700 px-3 py-1.5 rounded-full border border-amber-200">
            <ClockIcon className="h-3.5 w-3.5" />
            {enAttente} doc(s) en attente
          </div>
        )}
      </div>

      {/* Onglets */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit flex-wrap">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setOnglet(t.key)}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all relative',
              onglet === t.key ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
            {t.icon}{t.label}
            {t.key === 'documents' && enAttente > 0 && (
              <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-xs w-4 h-4 rounded-full flex items-center justify-center">
                {enAttente}
              </span>
            )}
          </button>
        ))}
      </div>

      {onglet === 'dashboard' && <OngletDashboard />}

      {onglet === 'portail' && (
        <div className="max-w-2xl bg-white border border-gray-200 rounded-xl p-6">
          <PortailCourtier onEnvoi={ajouterDocument} />
        </div>
      )}

      {onglet === 'documents' && (
        <div className="max-w-3xl">
          <DocumentsRecus documents={documents} onUpdate={updateDocument} />
        </div>
      )}

      {onglet === 'commissions' && <OngletCommissions />}
    </div>
  )
}

// ─── Onglet Courtiers autonome (Souscription / Sinistres / Réassurance) ────────

export function OngletCourtiers({ categorieFiltre }: { categorieFiltre?: DocumentCourtier['categorie'] }) {
  const [documents, setDocuments] = useState<DocumentCourtier[]>(
    categorieFiltre ? DEMO_DOCUMENTS.filter(d => d.categorie === categorieFiltre) : DEMO_DOCUMENTS
  )
  const updateDocument = (d: DocumentCourtier) =>
    setDocuments(prev => prev.map(dd => dd.id === d.id ? d : dd))

  return <DocumentsRecus documents={documents} onUpdate={updateDocument} categorieFiltre={categorieFiltre} />
}

// Export du composant DocumentsRecus pour réutilisation dans Souscription/Sinistres/Réassurance
export { DocumentsRecus }
export type { DocumentCourtier }
