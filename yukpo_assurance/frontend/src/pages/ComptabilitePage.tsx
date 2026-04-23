import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  DocumentTextIcon,
  CloudArrowUpIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  BanknotesIcon,
  ReceiptRefundIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  ArrowDownTrayIcon,
  XMarkIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline'
import { DemoBanner } from '../components/DemoBanner'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, ResponsiveContainer, Legend,
} from 'recharts'
import axios from 'axios'
import { ArchiveNumerique } from '../components/ArchiveNumerique'
import { RapportsModule } from '../components/RapportsModule'
import { CorrespondancesModule } from '../components/CorrespondancesModule'

// ─── Types ─────────────────────────────────────────────────────────────────

interface PieceAnalysee {
  id: string
  fichier: string
  type: string
  statut: 'en_attente' | 'analyse' | 'valide' | 'erreur'
  montant_ttc?: number
  montant_ht?: number
  tva?: number
  fournisseur?: string
  date_facture?: string
  numero_facture?: string
  compte_pcsa?: string
  champs_orass?: Record<string, string>
  confiance?: number
  erreur?: string
}

interface LigneBancaire {
  date: string
  libelle: string
  debit: number
  credit: number
  solde: number
  rapprochee: boolean
  ecriture_comptable?: string
}

interface StatCompta {
  total_pieces: number
  montant_total: number
  rapprochees: number
  ecarts: number
  taux_rapprochement: number
}

// ─── Données démo ──────────────────────────────────────────────────────────

const PIECES_DEMO: PieceAnalysee[] = [
  {
    id: '1',
    fichier: 'facture_garage_toyota_2024.pdf',
    type: 'facture_garage',
    statut: 'valide',
    montant_ttc: 485000,
    montant_ht: 420000,
    tva: 65000,
    fournisseur: 'Garage Toyota Douala',
    date_facture: '2024-03-15',
    numero_facture: 'FAC-2024-0892',
    compte_pcsa: '6150',
    confiance: 0.94,
    champs_orass: { SINISTRE_ID: 'SIN-2024-0234', VEHICULE_MARQUE: 'Toyota', REPARATION_TYPE: 'Carrosserie' },
  },
  {
    id: '2',
    fichier: 'facture_clinique_centrale.pdf',
    type: 'facture_hopital',
    statut: 'valide',
    montant_ttc: 1250000,
    montant_ht: 1250000,
    tva: 0,
    fournisseur: 'Clinique Centrale de Yaoundé',
    date_facture: '2024-03-18',
    numero_facture: 'CLQ-2024-1156',
    compte_pcsa: '6180',
    confiance: 0.91,
    champs_orass: { SINISTRE_ID: 'SIN-2024-0198', PATIENT_NOM: 'MBARGA J.', DIAGNOSTIC: 'Fracture tibia' },
  },
  {
    id: '3',
    fichier: 'constat_amiable_scan.jpg',
    type: 'constat_amiable',
    statut: 'valide',
    montant_ttc: 0,
    fournisseur: '-',
    date_facture: '2024-03-10',
    compte_pcsa: '-',
    confiance: 0.88,
    champs_orass: { SINISTRE_ID: 'SIN-2024-0276', CONDUCTEUR_A: 'NKENG P.', CONDUCTEUR_B: 'FOGUE H.' },
  },
  {
    id: '4',
    fichier: 'rapport_expertise_auto.pdf',
    type: 'rapport_expertise_auto',
    statut: 'valide',
    montant_ttc: 3200000,
    montant_ht: 3200000,
    tva: 0,
    fournisseur: 'Cabinet Expertise ALLO-EXPERTISE',
    date_facture: '2024-03-20',
    numero_facture: 'EXP-2024-0045',
    compte_pcsa: '6160',
    confiance: 0.96,
    champs_orass: { SINISTRE_ID: 'SIN-2024-0234', VALEUR_VENALE: '4500000', TAUX_DOMMAGE: '71%' },
  },
]

const LIGNES_BANCAIRES_DEMO: LigneBancaire[] = [
  { date: '2024-03-01', libelle: 'VIREMENT REASS SCOR 2024Q1', debit: 0, credit: 45000000, solde: 145000000, rapprochee: true, ecriture_comptable: 'Cession réassurance Q1' },
  { date: '2024-03-05', libelle: 'PAIEMENT SINISTRE SIN-2024-0198', debit: 1250000, credit: 0, solde: 143750000, rapprochee: true, ecriture_comptable: 'Sinistre corporel CLQ-2024-1156' },
  { date: '2024-03-10', libelle: 'PRIME RECU COMT-2024-1892', debit: 0, credit: 850000, solde: 144600000, rapprochee: true, ecriture_comptable: 'Encaissement prime auto' },
  { date: '2024-03-15', libelle: 'PAIEMENT GARAGE TOYOTA', debit: 485000, credit: 0, solde: 144115000, rapprochee: true, ecriture_comptable: 'Réparation SIN-2024-0234' },
  { date: '2024-03-18', libelle: 'CHARGES DIVERSES BUREAU', debit: 125000, credit: 0, solde: 143990000, rapprochee: false },
  { date: '2024-03-20', libelle: 'VIREMENT INTERNE PROVISIONS', debit: 5000000, credit: 0, solde: 138990000, rapprochee: false },
  { date: '2024-03-22', libelle: 'PRIMES COURTIER YAOUNDE', debit: 0, credit: 2340000, solde: 141330000, rapprochee: true, ecriture_comptable: 'Encaissement via courtier' },
  { date: '2024-03-25', libelle: 'SALAIRES MARS 2024', debit: 8500000, credit: 0, solde: 132830000, rapprochee: true, ecriture_comptable: 'Masse salariale 03/2024' },
]

const EVOLUTION_DEMO = [
  { mois: 'Oct', charges: 12.5, primes: 18.2, sinistres: 8.4 },
  { mois: 'Nov', charges: 11.8, primes: 19.1, sinistres: 9.2 },
  { mois: 'Déc', charges: 15.2, primes: 22.5, sinistres: 12.1 },
  { mois: 'Jan', charges: 13.1, primes: 20.3, sinistres: 10.5 },
  { mois: 'Fév', charges: 12.9, primes: 21.7, sinistres: 9.8 },
  { mois: 'Mar', charges: 14.2, primes: 23.4, sinistres: 11.3 },
]

const TYPES_PIECES = [
  { value: 'facture_garage', label: 'Facture Garage / Réparation' },
  { value: 'facture_hopital', label: 'Facture Hôpital / Clinique' },
  { value: 'constat_amiable', label: 'Constat Amiable' },
  { value: 'rapport_expertise_auto', label: "Rapport d'Expertise Auto" },
  { value: 'certificat_medical', label: 'Certificat Médical' },
  { value: 'facture_fournisseur', label: 'Facture Fournisseur' },
  { value: 'devis', label: 'Devis / Pro-forma' },
]

// ─── Composant principal ───────────────────────────────────────────────────

export default function ComptabilitePage() {
  const [pieces, setPieces] = useState<PieceAnalysee[]>(PIECES_DEMO)
  const [lignesBancaires] = useState<LigneBancaire[]>(LIGNES_BANCAIRES_DEMO)
  const [pieceSelectionnee, setPieceSelectionnee] = useState<PieceAnalysee | null>(null)
  const [typePiece, setTypePiece] = useState('facture_garage')
  const [uploading, setUploading] = useState(false)
  const [onglet, setOnglet] = useState<'ocr' | 'rapprochement' | 'analytique' | 'fournisseurs' | 'correspondances' | 'archive' | 'rapports'>('ocr')
  const [rechercheBancaire, setRechercheBancaire] = useState('')

  const stats: StatCompta = {
    total_pieces: pieces.length,
    montant_total: pieces.reduce((s, p) => s + (p.montant_ttc || 0), 0),
    rapprochees: lignesBancaires.filter(l => l.rapprochee).length,
    ecarts: lignesBancaires.filter(l => !l.rapprochee).length,
    taux_rapprochement: Math.round((lignesBancaires.filter(l => l.rapprochee).length / lignesBancaires.length) * 100),
  }

  // ─── Upload & analyse OCR ─────────────────────────────────────────────

  const onDrop = useCallback(async (fichiers: File[]) => {
    setUploading(true)
    for (const fichier of fichiers) {
      const nouvellePiece: PieceAnalysee = {
        id: Date.now().toString(),
        fichier: fichier.name,
        type: typePiece,
        statut: 'analyse',
      }
      setPieces(prev => [...prev, nouvellePiece])

      try {
        const formData = new FormData()
        formData.append('fichier', fichier)
        formData.append('type_document', typePiece)

        const res = await axios.post('/api/v1/comptabilite/analyser-piece', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })

        setPieces(prev => prev.map(p =>
          p.id === nouvellePiece.id
            ? { ...nouvellePiece, ...(res.data as object), statut: 'valide' as const }
            : p
        ))
      } catch {
        // Demo fallback
        const demoData = genererDemoPiece(fichier.name, typePiece, nouvellePiece.id)
        setPieces(prev => prev.map(p =>
          p.id === nouvellePiece.id ? demoData : p
        ))
      }
    }
    setUploading(false)
  }, [typePiece])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'image/*': ['.jpg', '.jpeg', '.png'] },
    multiple: true,
  })

  const genererDemoPiece = (nom: string, type: string, id: string): PieceAnalysee => ({
    id,
    fichier: nom,
    type,
    statut: 'valide',
    montant_ttc: Math.round(Math.random() * 500000 + 50000),
    montant_ht: Math.round(Math.random() * 430000 + 45000),
    tva: Math.round(Math.random() * 70000),
    fournisseur: 'Fournisseur extrait par OCR',
    date_facture: new Date().toISOString().split('T')[0],
    numero_facture: `FAC-${Date.now().toString().slice(-6)}`,
    compte_pcsa: type === 'facture_garage' ? '6150' : type === 'facture_hopital' ? '6180' : '6199',
    confiance: 0.85 + Math.random() * 0.12,
    champs_orass: { DOCUMENT_OCR: 'OK', SOURCE: 'reconnaissance visuelle YukpoPro' },
  })

  const fmt = (n: number) => n.toLocaleString('fr-FR') + ' XAF'

  const statutBadge = (statut: string) => {
    const classes: Record<string, string> = {
      valide: 'bg-green-100 text-green-700',
      analyse: 'bg-blue-100 text-blue-700',
      en_attente: 'bg-gray-100 text-gray-600',
      erreur: 'bg-red-100 text-red-700',
    }
    const labels: Record<string, string> = {
      valide: 'Validé', analyse: 'Analyse…', en_attente: 'En attente', erreur: 'Erreur',
    }
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${classes[statut] || ''}`}>
        {labels[statut] || statut}
      </span>
    )
  }

  const lignesFiltrees = lignesBancaires.filter(l =>
    l.libelle.toLowerCase().includes(rechercheBancaire.toLowerCase())
  )

  return (
    <div className="space-y-6">

      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Comptabilité</h1>
          <p className="text-sm text-gray-500 mt-1">OCR pièces comptables · Rapprochement bancaire · Analytique charges</p>
          <DemoBanner className="mt-2" />
        </div>
        <button className="flex items-center gap-2 text-sm bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
          <ArrowDownTrayIcon className="w-4 h-4" />
          Exporter PCSA
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Pièces analysées', value: stats.total_pieces.toString(), icon: DocumentTextIcon, color: 'text-blue-600 bg-blue-50' },
          { label: 'Montant total', value: fmt(stats.montant_total), icon: BanknotesIcon, color: 'text-green-600 bg-green-50' },
          { label: 'Rapprochées', value: `${stats.rapprochees}/${lignesBancaires.length}`, icon: CheckCircleIcon, color: 'text-primary-600 bg-primary-50' },
          { label: 'Taux rapprochement', value: `${stats.taux_rapprochement}%`, icon: ReceiptRefundIcon, color: 'text-purple-600 bg-purple-50' },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3">
            <div className={`${k.color} p-2 rounded-lg flex-shrink-0`}>
              <k.icon className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-gray-500">{k.label}</p>
              <p className="text-sm font-bold text-gray-900">{k.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Onglets */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {[
            { key: 'ocr', label: 'OCR Pièces comptables', icon: DocumentTextIcon },
            { key: 'rapprochement', label: 'Rapprochement bancaire', icon: BanknotesIcon },
            { key: 'analytique', label: 'Analytique charges', icon: ReceiptRefundIcon },
            { key: 'fournisseurs', label: 'Fournisseurs', icon: ArrowDownTrayIcon },
            { key: 'correspondances', label: 'Correspondances', icon: PencilSquareIcon },
            { key: 'archive', label: 'Archive', icon: FunnelIcon },
            { key: 'rapports', label: 'Rapports', icon: DocumentTextIcon },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setOnglet(t.key as typeof onglet)}
              className={`flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-colors ${
                onglet === t.key
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Onglet OCR ─────────────────────────────────────────────────── */}
      {onglet === 'ocr' && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          {/* Upload zone + liste */}
          <div className="xl:col-span-2 space-y-4">

            {/* Sélection type */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">Type de document</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {TYPES_PIECES.map(t => (
                  <button
                    key={t.value}
                    onClick={() => setTypePiece(t.value)}
                    className={`text-xs px-3 py-2 rounded-lg border text-left transition-colors ${
                      typePiece === t.value
                        ? 'border-primary-500 bg-primary-50 text-primary-700 font-medium'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Drop zone */}
            <div
              {...getRootProps()}
              className={`rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-300 hover:border-gray-400 bg-white'
              }`}
            >
              <input {...getInputProps()} />
              <CloudArrowUpIcon className={`w-10 h-10 mx-auto mb-2 ${isDragActive ? 'text-primary-500' : 'text-gray-400'}`} />
              {uploading ? (
                <p className="text-sm text-blue-600 flex items-center justify-center gap-2">
                  <ArrowPathIcon className="w-4 h-4 animate-spin" />
                  Analyse OCR en cours (reconnaissance visuelle YukpoPro)…
                </p>
              ) : isDragActive ? (
                <p className="text-sm text-primary-600 font-medium">Déposer les fichiers ici…</p>
              ) : (
                <>
                  <p className="text-sm text-gray-600">Glisser-déposer vos pièces ou <span className="text-primary-600 font-medium">cliquer pour choisir</span></p>
                  <p className="text-xs text-gray-400 mt-1">PDF, JPG, PNG — max 20 MB</p>
                </>
              )}
            </div>

            {/* Tableau pièces */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-800">Pièces analysées</h3>
                <span className="text-xs text-gray-400">{pieces.length} document(s)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Document</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Type</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Montant TTC</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Compte PCSA</th>
                      <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Confiance</th>
                      <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Statut</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {pieces.map((p) => (
                      <tr
                        key={p.id}
                        className="hover:bg-gray-50 cursor-pointer transition-colors"
                        onClick={() => setPieceSelectionnee(p)}
                      >
                        <td className="px-4 py-2.5">
                          <p className="text-gray-800 font-medium truncate max-w-[180px]">{p.fichier}</p>
                          <p className="text-gray-400 text-xs">{p.fournisseur}</p>
                        </td>
                        <td className="px-4 py-2.5 text-gray-600 text-xs">{TYPES_PIECES.find(t => t.value === p.type)?.label || p.type}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-gray-900">
                          {p.montant_ttc ? fmt(p.montant_ttc) : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-gray-600 font-mono text-xs">{p.compte_pcsa || '—'}</td>
                        <td className="px-4 py-2.5 text-center">
                          {p.confiance ? (
                            <span className={`text-xs font-medium ${p.confiance > 0.9 ? 'text-green-600' : p.confiance > 0.8 ? 'text-yellow-600' : 'text-red-500'}`}>
                              {Math.round(p.confiance * 100)}%
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-center">{statutBadge(p.statut)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Panneau détail */}
          <div className="xl:col-span-1">
            {pieceSelectionnee ? (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 sticky top-4">
                <div className="flex items-start justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-800">Détail OCR</h3>
                  <button onClick={() => setPieceSelectionnee(null)}>
                    <XMarkIcon className="w-4 h-4 text-gray-400 hover:text-gray-600" />
                  </button>
                </div>

                <div className="space-y-3">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Fichier</p>
                    <p className="text-sm font-medium text-gray-800 break-all">{pieceSelectionnee.fichier}</p>
                  </div>

                  {[
                    { label: 'Fournisseur', value: pieceSelectionnee.fournisseur },
                    { label: 'N° Facture', value: pieceSelectionnee.numero_facture },
                    { label: 'Date', value: pieceSelectionnee.date_facture },
                    { label: 'Montant HT', value: pieceSelectionnee.montant_ht != null ? fmt(pieceSelectionnee.montant_ht) : undefined },
                    { label: 'TVA', value: pieceSelectionnee.tva != null ? fmt(pieceSelectionnee.tva) : undefined },
                    { label: 'Montant TTC', value: pieceSelectionnee.montant_ttc != null ? fmt(pieceSelectionnee.montant_ttc) : undefined },
                    { label: 'Compte PCSA', value: pieceSelectionnee.compte_pcsa },
                  ].filter(f => f.value).map(f => (
                    <div key={f.label} className="flex justify-between text-sm">
                      <span className="text-gray-500">{f.label}</span>
                      <span className="font-medium text-gray-800">{f.value}</span>
                    </div>
                  ))}

                  {pieceSelectionnee.confiance && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Confiance IA</span>
                      <span className={`font-bold ${pieceSelectionnee.confiance > 0.9 ? 'text-green-600' : 'text-yellow-600'}`}>
                        {Math.round(pieceSelectionnee.confiance * 100)}%
                      </span>
                    </div>
                  )}

                  {/* Champs ORASS */}
                  {pieceSelectionnee.champs_orass && Object.keys(pieceSelectionnee.champs_orass).length > 0 && (
                    <div className="border-t border-gray-100 pt-3">
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Champs ORASS</p>
                      <div className="space-y-1">
                        {Object.entries(pieceSelectionnee.champs_orass).map(([k, v]) => (
                          <div key={k} className="flex justify-between text-xs">
                            <span className="text-gray-400 font-mono">{k}</span>
                            <span className="text-gray-700 font-medium">{v}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2 pt-2">
                    <button className="flex-1 text-xs py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors">
                      Valider & Imputer
                    </button>
                    <button className="flex-1 text-xs py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors">
                      Corriger
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center">
                <DocumentTextIcon className="w-10 h-10 text-gray-200 mx-auto mb-2" />
                <p className="text-sm text-gray-400">Cliquer sur une pièce pour voir le détail OCR</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Onglet Rapprochement bancaire ─────────────────────────────── */}
      {onglet === 'rapprochement' && (
        <div className="space-y-4">

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="relative flex-1">
                <MagnifyingGlassIcon className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={rechercheBancaire}
                  onChange={e => setRechercheBancaire(e.target.value)}
                  placeholder="Rechercher dans les opérations…"
                  className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <button className="flex items-center gap-2 text-sm border border-gray-300 rounded-lg px-3 py-2 text-gray-600 hover:bg-gray-50">
                <FunnelIcon className="w-4 h-4" />
                Filtres
              </button>
            </div>

            {/* Résumé rapprochement */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-green-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Rapprochées</p>
                <p className="text-lg font-bold text-green-600">{stats.rapprochees}</p>
              </div>
              <div className="bg-red-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Non rapprochées</p>
                <p className="text-lg font-bold text-red-600">{stats.ecarts}</p>
              </div>
              <div className="bg-primary-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Taux</p>
                <p className="text-lg font-bold text-primary-600">{stats.taux_rapprochement}%</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Date</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Libellé</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Débit</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Crédit</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Solde</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Écriture comptable</th>
                    <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Statut</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {lignesFiltrees.map((l, i) => (
                    <tr key={i} className={`${i % 2 === 0 ? '' : 'bg-gray-50'} hover:bg-blue-50 transition-colors`}>
                      <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">{l.date}</td>
                      <td className="px-4 py-2.5 text-gray-800 max-w-[220px] truncate" title={l.libelle}>{l.libelle}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-red-600">
                        {l.debit > 0 ? fmt(l.debit) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-green-600">
                        {l.credit > 0 ? fmt(l.credit) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-gray-900">{fmt(l.solde)}</td>
                      <td className="px-4 py-2.5 text-gray-500 text-xs max-w-[200px] truncate">
                        {l.ecriture_comptable || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {l.rapprochee ? (
                          <span className="flex items-center justify-center gap-1 text-xs text-green-600">
                            <CheckCircleIcon className="w-3.5 h-3.5" /> OK
                          </span>
                        ) : (
                          <span className="flex items-center justify-center gap-1 text-xs text-amber-600">
                            <ExclamationTriangleIcon className="w-3.5 h-3.5" /> À vérifier
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── Onglet Analytique ─────────────────────────────────────────── */}
      {onglet === 'analytique' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">Évolution charges vs primes (M XAF)</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={EVOLUTION_DEMO}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="mois" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={v => v + 'M'} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v: number) => `${v}M XAF`} />
                <Legend />
                <Line type="monotone" dataKey="primes" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} name="Primes encaissées" />
                <Line type="monotone" dataKey="sinistres" stroke="#ef4444" strokeWidth={2} dot={{ r: 4 }} name="Charges sinistres" />
                <Line type="monotone" dataKey="charges" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} name="Charges générales" strokeDasharray="4 4" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">Répartition charges par compte PCSA</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={[
                { compte: '6150 Répar.', montant: 485 },
                { compte: '6160 Expertise', montant: 320 },
                { compte: '6180 Médical', montant: 1250 },
                { compte: '6199 Divers', montant: 125 },
                { compte: '6210 Salaires', montant: 8500 },
                { compte: '6310 Réassur.', montant: 2100 },
              ]} barSize={30}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="compte" tick={{ fontSize: 10 }} interval={0} />
                <YAxis tickFormatter={v => v + 'k'} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number) => `${v} 000 XAF`} />
                <Bar dataKey="montant" fill="#6366f1" radius={[4, 4, 0, 0]} name="Montant (kXAF)" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Top fournisseurs */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 lg:col-span-2">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">Top fournisseurs — Trimestre en cours</h3>
            <div className="space-y-3">
              {[
                { nom: 'Garage Toyota Douala', type: 'Réparation auto', montant: 4850000, nb: 12 },
                { nom: 'Clinique Centrale Yaoundé', type: 'Soins médicaux', montant: 8750000, nb: 7 },
                { nom: 'Cabinet ALLO-EXPERTISE', type: 'Expertise automobile', montant: 3200000, nb: 5 },
                { nom: 'Pharmacie du Plateau', type: 'Médicaments', montant: 1250000, nb: 23 },
                { nom: 'Hôpital Général Douala', type: 'Soins médicaux', montant: 6400000, nb: 4 },
              ].map((f, i) => (
                <div key={i} className="flex items-center gap-4">
                  <span className="text-sm text-gray-400 w-4">{i + 1}</span>
                  <div className="flex-1">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm text-gray-800 font-medium">{f.nom}</span>
                      <span className="text-sm font-bold text-gray-900">{fmt(f.montant)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                        <div
                          className="bg-primary-500 h-1.5 rounded-full"
                          style={{ width: `${(f.montant / 8750000) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400">{f.nb} fact.</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Onglet Fournisseurs (affaires générales) ──────────────────── */}
      {onglet === 'fournisseurs' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
              <ArrowDownTrayIcon className="h-5 w-5 text-indigo-600" />
              Pièces reçues des fournisseurs — Affaires générales
            </h3>
            <p className="text-xs text-gray-500 mb-4">Documents transmis par les prestataires externes (garages, cliniques, experts, etc.) en lien avec les dossiers de la compagnie.</p>
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: 'Pièces en attente', value: '4', cls: 'border-amber-200 bg-amber-50 text-amber-700' },
                { label: 'Importées ORASS', value: '23', cls: 'border-green-200 bg-green-50 text-green-700' },
                { label: 'Montant total traité', value: '28.5 M XAF', cls: 'border-blue-200 bg-blue-50 text-blue-700' },
              ].map((k, i) => (
                <div key={i} className={`border rounded-xl p-4 text-center ${k.cls}`}>
                  <p className="text-xl font-bold">{k.value}</p>
                  <p className="text-xs mt-0.5">{k.label}</p>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    {['Fournisseur', 'Type', 'Référence sinistre', 'Montant TTC', 'Score', 'Statut', 'Actions'].map(h => (
                      <th key={h} className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {[
                    { fourn: 'Garage Central YDE', type: 'Garage', ref: 'SIN-2026-0342', montant: '485 000', score: 88, statut: 'en_attente' },
                    { fourn: 'Clinique Les Sœurs', type: 'Clinique', ref: 'SIN-2026-0289', montant: '1 250 000', score: 78, statut: 'valide' },
                    { fourn: 'Expert SARL', type: 'Expert', ref: 'SIN-2026-0301', montant: '3 200 000', score: 92, statut: 'valide' },
                    { fourn: 'Pharmacie du Centre', type: 'Pharmacie', ref: 'SIN-2026-0255', montant: '185 000', score: 34, statut: 'rejete' },
                  ].map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="py-3 px-3 font-medium text-gray-900">{r.fourn}</td>
                      <td className="py-3 px-3 text-gray-500">{r.type}</td>
                      <td className="py-3 px-3 font-mono text-primary-600 text-xs">{r.ref}</td>
                      <td className="py-3 px-3 font-semibold text-gray-900">{r.montant} XAF</td>
                      <td className="py-3 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${r.score >= 70 ? 'bg-green-100 text-green-700' : r.score >= 45 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                          {r.score}/100
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${r.statut === 'en_attente' ? 'bg-amber-100 text-amber-700' : r.statut === 'valide' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                          {r.statut === 'en_attente' ? 'En attente' : r.statut === 'valide' ? 'Validé' : 'Rejeté'}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        {r.statut === 'en_attente' && (
                          <button className="text-xs bg-primary-600 text-white px-2.5 py-1 rounded-lg hover:bg-primary-700 transition-colors">
                            Valider → ORASS
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── Onglet Correspondances ───────────────────────────────────────── */}
      {onglet === 'correspondances' && (
        <CorrespondancesModule
          module="comptabilite"
          titre="Correspondances — Comptabilité"
        />
      )}

      {/* ── Onglet Archive ────────────────────────────────────────────── */}
      {onglet === 'archive' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FunnelIcon className="h-5 w-5 text-primary-600" />
            Archive numérique — Comptabilité
          </h3>
          <ArchiveNumerique module="comptabilite" hauteurMax="500px" />
        </div>
      )}

      {/* ── Onglet Rapports ───────────────────────────────────────────── */}
      {onglet === 'rapports' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <RapportsModule module="comptabilite" />
        </div>
      )}
    </div>
  )
}
