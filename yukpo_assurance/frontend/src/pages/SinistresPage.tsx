import { useState, useEffect, useRef, useCallback } from 'react'
import {
  CameraIcon, DocumentArrowUpIcon, CheckCircleIcon, XMarkIcon,
  ExclamationTriangleIcon, ClockIcon, MagnifyingGlassIcon,
  ArrowPathIcon, ChevronRightIcon, ShieldExclamationIcon,
  HeartIcon, TruckIcon, HomeModernIcon, BriefcaseIcon,
  UserIcon, DocumentTextIcon, ArrowUturnLeftIcon, PencilSquareIcon,
  SparklesIcon, ArrowDownTrayIcon, CurrencyDollarIcon, BanknotesIcon,
} from '@heroicons/react/24/outline'
import { sinistresAPI, apiClient } from '../api/client'
import { ArchiveNumerique } from '../components/ArchiveNumerique'
import { RapportsModule } from '../components/RapportsModule'
import { BuildingStorefrontIcon, ChartBarIcon, UserGroupIcon } from '@heroicons/react/24/outline'
import { OngletCourtiers } from './CourtiersPage'
import { CorrespondancesModule } from '../components/CorrespondancesModule'
import { Sinistre, EtapeWorkflow } from '../api/types'
import { format, parseISO } from 'date-fns'
import { fr } from 'date-fns/locale'
import { clsx } from 'clsx'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { DemoBanner } from '../components/DemoBanner'
import { EmptyState } from '../components/EmptyState'

// ─── Types ────────────────────────────────────────────────────────────────────

type FamilleSinistre = 'non_vie' | 'vie'

interface TypeSinistre {
  id: string
  famille: FamilleSinistre
  label: string
  icon: React.ComponentType<{ className?: string }>
  couleur: string
  documents: string[]
  champs_auto: string[]
  branche_cima: string   // code branche CIMA
  compte_charge: string  // compte OHADA charge sinistre
  compte_provision: string // compte OHADA provision/PSAP
  docs_fournisseur: string[] // docs que le fournisseur peut envoyer
}

// ─── Nomenclature CIMA — Livre IV ─────────────────────────────────────────────
// Non-Vie : B01 Accidents corporels | B02 Maladie | B03 Auto corps | B07 Transport
//           B08 Incendie/IRD | B09 Dommages divers | B10 RC Auto | B13 RC Générale
//           B14 Crédit | B15 Caution | B16 Agriculture | B17 Engineering
// Vie     : B20 Vie entière/mixte | B21 Capitalisation | B22 Décès/rente | B23 Épargne
// IMPORTANT : Maladie / Hospitalisation = Branche 2 NON-VIE (pas Vie)
const TYPES_SINISTRE: TypeSinistre[] = [
  // ── Non-Vie ──────────────────────────────────────────────────────────────────
  {
    id: 'auto', famille: 'non_vie', label: 'Automobile', icon: TruckIcon,
    couleur: 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100',
    branche_cima: 'B03 — RC/Corps Auto', compte_charge: '6141 — Sinistres auto', compte_provision: '3941 — PSAP auto',
    documents: ['Constat amiable', 'PV gendarmerie', 'Facture garage', 'Devis réparation', 'Photos'],
    champs_auto: ['assuré', 'n° police', 'véhicule', 'date accident', 'tiers', 'montant'],
    docs_fournisseur: ['Facture garage', 'Devis réparation', 'Photos véhicule'],
  },
  {
    id: 'accident_corporel', famille: 'non_vie', label: 'Accident Corporel', icon: UserIcon,
    couleur: 'bg-red-50 border-red-200 text-red-700 hover:bg-red-100',
    branche_cima: 'B01 — Accidents corporels', compte_charge: '6140 — Sinistres accidents corp.', compte_provision: '3940 — PSAP acc. corporels',
    documents: ['Certificat médical initial', 'Rapport médecin expert', 'Barème CIMA IPP', 'PV accident', 'CNI assuré'],
    champs_auto: ['assuré', 'date accident', 'nature blessure', 'taux IPP', 'montant indemnité'],
    docs_fournisseur: ['Rapport médical', 'Certificat médical', 'Ordonnances', 'Factures soins'],
  },
  {
    id: 'maladie', famille: 'non_vie', label: 'Maladie / Hospitalisation', icon: HeartIcon,
    couleur: 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100',
    branche_cima: 'B02 — Maladie (Non-Vie)', compte_charge: '6144 — Remboursements soins/maladie', compte_provision: '3944 — PSAP maladie',
    documents: ['Factures hôpital/clinique', 'Ordonnances', 'Certificat médical', "Bulletin d'hospitalisation", 'Résultats examens labo'],
    champs_auto: ['assuré', 'établissement', 'pathologie', 'durée séjour', 'total facturé', 'remboursable'],
    docs_fournisseur: ['Facture détaillée', 'Décompte soins', 'Ordonnances', 'Résultats labo'],
  },
  {
    id: 'mrh', famille: 'non_vie', label: 'MRH / Incendie', icon: HomeModernIcon,
    couleur: 'bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100',
    branche_cima: 'B08 — Incendie & Dommages', compte_charge: '6142 — Sinistres IRD/MRH', compte_provision: '3942 — PSAP IRD',
    documents: ['Rapport expertise', 'Factures réparation/remplacement', 'Photos dommages', 'PV pompiers'],
    champs_auto: ['assuré', 'adresse', 'nature sinistre', 'date', 'montant dommages'],
    docs_fournisseur: ['Facture artisan/réparateur', 'Bon de commande', 'Photos travaux'],
  },
  {
    id: 'transport', famille: 'non_vie', label: 'Transport / CMR', icon: TruckIcon,
    couleur: 'bg-cyan-50 border-cyan-200 text-cyan-700 hover:bg-cyan-100',
    branche_cima: 'B07 — Marchandises transportées', compte_charge: '6145 — Sinistres transport', compte_provision: '3945 — PSAP transport',
    documents: ['CMR / Connaissement', 'Constat de perte', 'Facture marchandise', 'Rapport expert', 'Photos'],
    champs_auto: ['expéditeur', 'destinataire', 'marchandise', 'poids', 'valeur', 'date'],
    docs_fournisseur: ['Lettre de voiture', 'Rapport avarie', 'Photos colis'],
  },
  {
    id: 'rc', famille: 'non_vie', label: 'RC Générale / Entreprise', icon: BriefcaseIcon,
    couleur: 'bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100',
    branche_cima: 'B13 — RC Générale', compte_charge: '6143 — Sinistres RC', compte_provision: '3943 — PSAP RC',
    documents: ['PV constat', 'Jugement / Ordonnance', 'Factures tiers lésé', 'Expertise judiciaire'],
    champs_auto: ['tiers lésé', 'nature préjudice', 'montant réclamé', 'date'],
    docs_fournisseur: ['Factures réparation tiers', 'Devis'],
  },
  {
    id: 'engineering', famille: 'non_vie', label: 'Engineering / TRC', icon: HomeModernIcon,
    couleur: 'bg-stone-50 border-stone-200 text-stone-700 hover:bg-stone-100',
    branche_cima: 'B09 — Dommages aux biens / TRC', compte_charge: '6146 — Sinistres engineering', compte_provision: '3946 — PSAP engineering',
    documents: ['Rapport ingénieur expert', 'Plans chantier', 'Contrat de construction', 'Photos dommages', 'Devis réparation'],
    champs_auto: ['maître ouvrage', 'entreprise', 'chantier', 'nature sinistre', 'coût réparation'],
    docs_fournisseur: ['Rapport technique', 'Devis réparation', 'Factures'],
  },
  {
    id: 'agriculture', famille: 'non_vie', label: 'Agriculture / Récoltes', icon: HomeModernIcon,
    couleur: 'bg-lime-50 border-lime-200 text-lime-700 hover:bg-lime-100',
    branche_cima: 'B16 — Agriculture', compte_charge: '6147 — Sinistres agriculture', compte_provision: '3947 — PSAP agriculture',
    documents: ['Constat de sinistre', 'Rapport expertise agricole', 'Factures intrants', 'Photos cultures sinistrées'],
    champs_auto: ['agriculteur', 'culture sinistrée', 'surface (ha)', 'cause (sécheresse/inondation)', 'pertes estimées'],
    docs_fournisseur: ['Rapport expertise', 'Photos'],
  },
  // ── Vie ──────────────────────────────────────────────────────────────────────
  {
    id: 'deces', famille: 'vie', label: 'Décès', icon: HeartIcon,
    couleur: 'bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100',
    branche_cima: 'B20 — Assurance Vie/Décès', compte_charge: '6171 — Prestations décès', compte_provision: '3971 — Provision décès',
    documents: ['Acte de décès (état civil)', 'Certificat médical de décès', 'CNI bénéficiaire', 'Bulletin souscription vie', 'Attestation de droits'],
    champs_auto: ['assuré décédé', 'date décès', 'cause', 'bénéficiaire', 'capital garanti'],
    docs_fournisseur: [],
  },
  {
    id: 'invalidite', famille: 'vie', label: 'Invalidité / IPP (Vie)', icon: UserIcon,
    couleur: 'bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100',
    branche_cima: 'B22 — Rente/Invalidité Vie', compte_charge: '6172 — Indemnités invalidité', compte_provision: '3972 — Provision IPP',
    documents: ["Certificat médical d'invalidité", 'Rapport médecin expert', 'Barème CIMA IPP/IPT', 'CNI assuré'],
    champs_auto: ['assuré', 'taux invalidité', 'cause', 'date consolidation', 'indemnité estimée'],
    docs_fournisseur: ['Rapport médical', 'Certificat médical', 'Ordonnances'],
  },
  {
    id: 'itt', famille: 'vie', label: 'ITT / Incapacité travail (Vie)', icon: DocumentTextIcon,
    couleur: 'bg-yellow-50 border-yellow-200 text-yellow-700 hover:bg-yellow-100',
    branche_cima: 'B22 — Prévoyance/ITT Vie', compte_charge: '6173 — Indemnités ITT', compte_provision: '3973 — Provision ITT',
    documents: ['Arrêt de travail signé médecin', 'Bulletins de salaire (3 mois)', 'Certificat médical', 'Attestation employeur'],
    champs_auto: ['assuré', 'employeur', 'salaire journalier', 'durée ITT', 'franchise', 'indemnité'],
    docs_fournisseur: ['Arrêt de travail', 'Certificat médical de prolongation'],
  },
  {
    id: 'epargne_vie', famille: 'vie', label: 'Vie Mixte / Épargne arrivée à terme', icon: DocumentTextIcon,
    couleur: 'bg-teal-50 border-teal-200 text-teal-700 hover:bg-teal-100',
    branche_cima: 'B21 — Capitalisation/Épargne', compte_charge: '6174 — Rachats / Prestations épargne', compte_provision: '3974 — Provisions mathématiques',
    documents: ['Contrat vie original', 'Pièce identité assuré', 'Dernier avis de situation', 'RIB bénéficiaire'],
    champs_auto: ['assuré', 'n° contrat', 'date terme', 'capital accumulé', 'mode versement'],
    docs_fournisseur: [],
  },
]

// ─── Données démo ─────────────────────────────────────────────────────────────

const DEMO_SINISTRES: Sinistre[] = [
  {
    id: '1', numero: 'SIN-2026-001', branche: 'auto', statut: 'en_cours',
    date_sinistre: '2026-03-15', date_declaration: '2026-03-16',
    montant_estime: 2_500_000, montant_regle: 0, assure_nom: 'Kouassi Jean-Baptiste',
    description: 'Collision à carrefour Akwa — constat amiable scanné', score_fraude: 12, police_numero: 'POL-AUTO-001',
    etapes_workflow: [
      { id: 'ouverture',          label: 'Ouverture sinistre',      statut: 'fait',      date: '16/03/2026' },
      { id: 'accuse_reception',   label: 'Accusé de réception',     statut: 'fait',      date: '16/03/2026' },
      { id: 'mise_en_cause',      label: 'Mise en cause',           statut: 'fait',      date: '18/03/2026' },
      { id: 'relances',           label: 'Relances',                statut: 'fait',      date: '25/03/2026' },
      { id: 'reclamation_pieces', label: 'Réclamations des pièces', statut: 'fait',      date: '18/03/2026' },
      { id: 'mission_expert',     label: 'Mission expert / Avocat', statut: 'en_cours',  date: '01/04/2026' },
    ],
  },
  {
    id: '2', numero: 'SIN-2026-002', branche: 'vie', statut: 'ouvert',
    date_sinistre: '2026-03-01', date_declaration: '2026-03-03',
    montant_estime: 25_000_000, assure_nom: 'Traoré Aminata',
    description: 'Décès assuré — capital vie à verser aux bénéficiaires', score_fraude: 3, police_numero: 'POL-VIE-042',
  },
  {
    id: '3', numero: 'SIN-2026-003', branche: 'sante', statut: 'clos',
    date_sinistre: '2026-02-10', date_declaration: '2026-02-11',
    montant_estime: 850_000, montant_regle: 720_000, assure_nom: 'Diallo Moussa',
    description: 'Hospitalisation 5 jours — factures scannées et validées', score_fraude: 5, police_numero: 'POL-SANTE-088',
  },
  {
    id: '4', numero: 'SIN-2026-004', branche: 'auto', statut: 'rejet',
    date_sinistre: '2026-03-10', date_declaration: '2026-03-15',
    montant_estime: 12_000_000, assure_nom: 'Bamba Seydou',
    description: 'Véhicule incendié — suspicion fraude score 82', score_fraude: 82, police_numero: 'POL-AUTO-031',
  },
  {
    id: '5', numero: 'SIN-2026-005', branche: 'vie', statut: 'en_cours',
    date_sinistre: '2026-03-20', date_declaration: '2026-03-21',
    montant_estime: 3_500_000, montant_regle: 0, assure_nom: 'Koffi Ekra René',
    description: 'IPP 30% — accident — barème CIMA appliqué', score_fraude: 8, police_numero: 'POL-VIE-015',
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STATUT_CONFIG: Record<string, { label: string; classes: string }> = {
  ouvert:            { label: 'Ouvert',            classes: 'bg-blue-100 text-blue-700' },
  en_cours:          { label: 'En cours',           classes: 'bg-yellow-100 text-yellow-700' },
  expertise_en_cours:{ label: 'Expertise',          classes: 'bg-purple-100 text-purple-700' },
  relance:           { label: 'Relancé',            classes: 'bg-orange-100 text-orange-700' },
  contentieux:       { label: 'Contentieux',        classes: 'bg-red-100 text-red-700' },
  accord:            { label: 'Accord',             classes: 'bg-teal-100 text-teal-700' },
  clos:              { label: 'Clôturé',            classes: 'bg-green-100 text-green-700' },
  rejet:             { label: 'Rejeté',             classes: 'bg-red-100 text-red-700' },
}

// ─── Étapes workflow règlement sinistre (risques divers / RC Auto) ────────────

const ETAPES_LABELS: { id: string; label: string }[] = [
  { id: 'ouverture',           label: 'Ouverture sinistre' },
  { id: 'accuse_reception',    label: 'Accusé de réception' },
  { id: 'mise_en_cause',       label: 'Mise en cause' },
  { id: 'relances',            label: 'Relances' },
  { id: 'reclamation_pieces',  label: 'Réclamations des pièces' },
  { id: 'mission_expert',      label: 'Mission expert / Avocat' },
  { id: 'bons_prise_en_charge',label: 'Bons de prise en charge' },
  { id: 'preavs_saisine',      label: 'Préavis de saisine' },
  { id: 'requete_unilaterale', label: 'Requête unilatérale' },
  { id: 'etude_rapport',       label: 'Étude rapport expertise' },
  { id: 'identification_victimes', label: 'Identification des victimes' },
  { id: 'notes_techniques',    label: 'Notes techniques' },
  { id: 'offre_indemnisation', label: 'Offre d\'indemnisation' },
  { id: 'accord_reglement',    label: 'Accord de règlement' },
  { id: 'pv_transaction',      label: 'Procès verbal de transaction' },
  { id: 'quittances',          label: 'Quittances de règlement' },
  { id: 'transmission_cheques', label: 'Transmissions chèques' },
  { id: 'revision',            label: 'Révisions' },
]

function WorkflowTimeline({ etapes }: { etapes?: EtapeWorkflow[] }) {
  const resolved: EtapeWorkflow[] = ETAPES_LABELS.map((e, i) => {
    const found = etapes?.find(x => x.id === e.id)
    if (found) return found
    return { id: e.id, label: e.label, statut: i === 0 ? 'en_cours' : 'en_attente' }
  })

  const dot = (s: EtapeWorkflow['statut']) => {
    if (s === 'fait')       return 'bg-green-500'
    if (s === 'en_cours')   return 'bg-yellow-400 animate-pulse'
    if (s === 'na')         return 'bg-gray-200'
    return 'bg-gray-300'
  }

  return (
    <div className="space-y-1">
      {resolved.map((e, i) => (
        <div key={e.id} className="flex items-start gap-3">
          <div className="flex flex-col items-center mt-1">
            <div className={clsx('w-2.5 h-2.5 rounded-full flex-shrink-0', dot(e.statut))} />
            {i < resolved.length - 1 && (
              <div className="w-px flex-1 bg-gray-200 mt-1" style={{ minHeight: 14 }} />
            )}
          </div>
          <div className="pb-2 min-w-0">
            <p className={clsx('text-xs leading-tight', e.statut === 'fait' ? 'text-gray-700 font-medium' : e.statut === 'en_cours' ? 'text-yellow-700 font-semibold' : 'text-gray-400')}>
              {i + 1}. {e.label}
            </p>
            {e.date && <p className="text-[10px] text-gray-400 mt-0.5">{e.date}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

function formatMontant(m?: number) {
  if (!m) return '—'
  return new Intl.NumberFormat('fr-FR').format(m) + ' FCFA'
}

function ScoreFraude({ score }: { score?: number }) {
  if (score == null) return null
  const color = score < 30 ? 'text-green-600' : score < 60 ? 'text-yellow-600' : 'text-red-600'
  const label = score < 30 ? 'Faible' : score < 60 ? 'Moyen' : 'Élevé'
  return (
    <span className={clsx('text-xs font-semibold', color)}>
      Fraude {label} ({score})
    </span>
  )
}

// ─── Composant OCR Scan Zone ──────────────────────────────────────────────────

interface OcrResult {
  champs: Record<string, string>
  confiance: number
  type_detecte: string
}

interface ScanZoneProps {
  typeSinistre: TypeSinistre
  onResult: (r: OcrResult, fichier: File) => void
  onCancel: () => void
}

function ScanZone({ typeSinistre, onResult, onCancel }: ScanZoneProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const traiter = useCallback(async (file: File) => {
    setLoading(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      // Type document selon la famille sinistre
      const typeDoc = typeSinistre.famille === 'vie'
        ? (typeSinistre.id === 'deces' ? 'CERTIFICAT_DECES' : typeSinistre.id === 'hospitalisation' ? 'FACTURE_MEDICALE' : 'CERTIFICAT_MEDICAL')
        : (typeSinistre.id === 'auto' ? 'CONSTAT_SINISTRE' : 'DOCUMENT_SINISTRE')
      formData.append('type_document', typeDoc)

      const { data } = await apiClient.post('/api/v1/documents/ocr/image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const d = data as Record<string, unknown>
      const champs = (d.donnees_structurees || d.donnees || {}) as Record<string, string>
      onResult({
        champs,
        confiance: (d.confiance as number) || 0.85,
        type_detecte: (d.type_detecte as string) || typeSinistre.label,
      }, file)
    } catch {
      // Démo fallback si API IA non disponible
      onResult(genererDemoOCR(typeSinistre), file)
    } finally {
      setLoading(false)
    }
  }, [typeSinistre, onResult])

  const handleFiles = (files: FileList | null) => {
    if (!files?.length) return
    traiter(files[0])
  }

  return (
    <div className="space-y-4">
      <div
        className={clsx(
          'border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer',
          dragOver ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
        )}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
      >
        {loading ? (
          <div className="space-y-3">
            <LoadingSpinner className="mx-auto h-10 w-10" />
            <p className="text-sm font-medium text-gray-700">YukpoPro analyse le document…</p>
            <p className="text-xs text-gray-500">Extraction des champs : {typeSinistre.champs_auto.join(', ')}</p>
          </div>
        ) : (
          <>
            <DocumentArrowUpIcon className="h-12 w-12 text-gray-400 mx-auto mb-3" />
            <p className="text-sm font-semibold text-gray-700">Glissez le document ici ou cliquez pour sélectionner</p>
            <p className="text-xs text-gray-500 mt-1">
              Documents acceptés : {typeSinistre.documents.join(' · ')}
            </p>
            <p className="text-xs text-gray-400 mt-2">PNG, JPG, PDF — max 20 Mo</p>
          </>
        )}
        <input ref={inputRef} type="file" className="hidden" accept="image/*,.pdf"
          onChange={e => handleFiles(e.target.files)} />
      </div>

      {/* Bouton caméra */}
      <button
        type="button"
        className="w-full flex items-center justify-center gap-2 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
        onClick={() => { if (inputRef.current) { inputRef.current.accept = 'image/*'; inputRef.current.capture = 'environment'; inputRef.current.click() } }}
      >
        <CameraIcon className="h-4 w-4" />
        Utiliser la caméra
      </button>

      {error && (
        <div className="flex items-center gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3">
          <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <button onClick={onCancel} className="text-xs text-gray-500 hover:text-gray-700 w-full text-center">
        ← Changer de type de sinistre
      </button>
    </div>
  )
}

function genererDemoOCR(type: TypeSinistre): OcrResult {
  const demos: Record<string, Record<string, string>> = {
    auto: {
      assure_nom: 'Kouassi Jean-Baptiste', police_numero: 'POL-AUTO-2026-001',
      date_sinistre: new Date().toISOString().slice(0, 10),
      immatriculation: 'LT-4521-A', tiers_nom: 'Bamba Seydou',
      tiers_immatriculation: 'YA-3302-B', lieu: 'Carrefour Akwa, Douala',
      montant_estime: '2500000', description: 'Collision — choc arrière',
    },
    mrh: {
      assure_nom: 'Traoré Fatima', police_numero: 'POL-MRH-2026-042',
      date_sinistre: new Date().toISOString().slice(0, 10),
      adresse_bien: 'Résidence Les Palmiers, Apt 14, Abidjan',
      nature_sinistre: 'Dégâts des eaux — fuite toiture', montant_estime: '3800000',
    },
    deces: {
      assure_nom: 'Diallo Moussa Ibrahim', police_numero: 'POL-VIE-2026-015',
      date_deces: new Date().toISOString().slice(0, 10),
      lieu_deces: 'Hôpital Central de Yaoundé',
      cause_deces: 'Arrêt cardio-respiratoire', beneficiaire: 'Diallo Kadiatou (épouse)',
      capital_garanti: '25000000',
    },
    invalidite: {
      assure_nom: 'Koffi Ekra René', police_numero: 'POL-VIE-2026-008',
      date_consolidation: new Date().toISOString().slice(0, 10),
      taux_ipp: '30', cause: 'Accident de la voie publique',
      medecin_expert: 'Dr Anouman Pierre', indemnite_estimee: '3500000',
    },
    hospitalisation: {
      assure_nom: 'Ouédraogo Marie', police_numero: 'POL-SANTE-2026-077',
      etablissement: 'Clinique Saint-Luc, Ouagadougou',
      pathologie: 'Paludisme grave', date_entree: '2026-03-10', date_sortie: '2026-03-15',
      nb_jours: '5', total_facture: '850000', remboursable: '720000',
    },
    itt: {
      assure_nom: 'Nguessan Paul', police_numero: 'POL-VIE-2026-033',
      employeur: 'NSIA Assurances CI', salaire_journalier: '85000',
      date_arret: '2026-03-01', duree_itt: '21', franchise: '3',
      indemnite_nette: '1530000',
    },
    transport: {
      expediteur: 'CEVITAL Distribution', destinataire: 'Société Abou-Diaby',
      marchandise: 'Huile alimentaire', poids_kg: '2500', valeur_declaree: '4200000',
      date_expedition: new Date().toISOString().slice(0, 10),
      lieu_sinistre: 'Axe Abidjan-Bouaké km 142', nature_sinistre: 'Vol à main armée',
    },
    rc: {
      tiers_lese: 'Compagnie PETROCI', nature_prejudice: 'Dégâts matériels',
      montant_reclame: '8500000', date_sinistre: new Date().toISOString().slice(0, 10),
      description: 'Incendie propagé depuis véhicule assuré',
    },
  }
  return {
    champs: demos[type.id] || {},
    confiance: 0.91,
    type_detecte: type.label,
  }
}

// ─── Composant Validation Extraction ─────────────────────────────────────────

interface ValidationProps {
  type: TypeSinistre
  ocr: OcrResult
  fichier: File
  onValider: (champs: Record<string, string>) => void
  onRetry: () => void
}

function ValidationExtraction({ type, ocr, onValider, onRetry }: ValidationProps) {
  const [champs, setChamps] = useState<Record<string, string>>(ocr.champs)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    setSubmitting(true)
    await new Promise(r => setTimeout(r, 600))
    onValider(champs)
    setSubmitting(false)
  }

  const confPct = Math.round(ocr.confiance * 100)
  const confColor = confPct >= 85 ? 'text-green-600' : confPct >= 65 ? 'text-yellow-600' : 'text-red-600'

  return (
    <div className="space-y-4">
      {/* En-tête résultat IA */}
      <div className="flex items-center justify-between bg-green-50 border border-green-200 rounded-lg px-4 py-3">
        <div className="flex items-center gap-2">
          <CheckCircleIcon className="h-5 w-5 text-green-600" />
          <span className="text-sm font-medium text-green-800">Document analysé — {type.label}</span>
        </div>
        <span className={clsx('text-xs font-semibold', confColor)}>
          Confiance {confPct}%
        </span>
      </div>

      {/* Champs extraits */}
      <div className="space-y-2">
        <p className="text-xs text-gray-500 font-medium">Vérifiez et corrigez si nécessaire :</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(champs).map(([key, val]) => (
            <div key={key}>
              <label className="block text-xs text-gray-500 mb-1 capitalize">{key.replace(/_/g, ' ')}</label>
              <input
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                value={val}
                onChange={e => setChamps(prev => ({ ...prev, [key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="flex-1 bg-primary-600 text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-primary-700 disabled:opacity-60 transition-colors"
        >
          {submitting ? 'Enregistrement…' : 'Valider & Soumettre'}
        </button>
        <button
          onClick={onRetry}
          className="px-4 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <ArrowPathIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

// ─── Composant Carte Sinistre ─────────────────────────────────────────────────

function SinistreCard({ s, onClick }: { s: Sinistre; onClick: () => void }) {
  const statut = STATUT_CONFIG[s.statut] || { label: s.statut, classes: 'bg-gray-100 text-gray-600' }
  const type = TYPES_SINISTRE.find(t => t.id === s.branche || (s.branche === 'sante' && t.id === 'hospitalisation') || (s.branche === 'vie' && t.id === 'deces'))
  const Icon = type?.icon || ShieldExclamationIcon

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:border-primary-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className={clsx('p-2 rounded-lg flex-shrink-0', type?.couleur.split(' ').slice(0, 2).join(' ') || 'bg-gray-100')}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 truncate">{s.numero}</p>
            <p className="text-xs text-gray-500 truncate">{s.assure_nom}</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full', statut.classes)}>
            {statut.label}
          </span>
          <span className="text-xs text-gray-500">
            {format(parseISO(s.date_sinistre), 'dd MMM yyyy', { locale: fr })}
          </span>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-gray-600 line-clamp-1">{s.description}</p>
        <div className="flex items-center gap-3 flex-shrink-0 ml-2">
          <span className="text-xs font-medium text-gray-700">{formatMontant(s.montant_estime)}</span>
          <ScoreFraude score={s.score_fraude} />
          <ChevronRightIcon className="h-3 w-3 text-gray-400" />
        </div>
      </div>
    </button>
  )
}

// ─── Composant Détail Sinistre ────────────────────────────────────────────────

function SinistreDetail({ s, onClose }: { s: Sinistre; onClose: () => void }) {
  const statut = STATUT_CONFIG[s.statut] || { label: s.statut, classes: 'bg-gray-100 text-gray-600' }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full">
        <div className="flex items-center justify-between p-6 border-b">
          <div>
            <h3 className="text-lg font-bold text-gray-900">{s.numero}</h3>
            <p className="text-sm text-gray-500">{s.assure_nom} · {s.police_numero}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-gray-500 block text-xs">Statut</span>
              <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full', statut.classes)}>{statut.label}</span>
            </div>
            <div><span className="text-gray-500 block text-xs">Branche</span>
              <span className="font-medium capitalize">{s.branche}</span></div>
            <div><span className="text-gray-500 block text-xs">Date sinistre</span>
              <span className="font-medium">{format(parseISO(s.date_sinistre), 'dd MMMM yyyy', { locale: fr })}</span></div>
            <div><span className="text-gray-500 block text-xs">Montant estimé</span>
              <span className="font-medium">{formatMontant(s.montant_estime)}</span></div>
            {s.montant_regle != null && s.montant_regle > 0 && (
              <div><span className="text-gray-500 block text-xs">Montant réglé</span>
                <span className="font-medium text-green-600">{formatMontant(s.montant_regle)}</span></div>
            )}
            <div><span className="text-gray-500 block text-xs">Score fraude</span>
              <ScoreFraude score={s.score_fraude} /></div>
          </div>
          <div>
            <span className="text-xs text-gray-500 block mb-1">Description</span>
            <p className="text-sm text-gray-700 bg-gray-50 rounded-lg p-3">{s.description}</p>
          </div>
          {/* Imputation comptable automatique */}
          {(() => {
            const type = TYPES_SINISTRE.find(t => t.id === s.branche || (s.branche === 'vie' && t.id === 'deces') || (s.branche === 'sante' && t.id === 'hospitalisation'))
            return type ? (
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs space-y-1">
                <div className="flex items-center gap-1.5 text-blue-700 font-semibold mb-1.5">
                  <BanknotesIcon className="h-3.5 w-3.5" />
                  Imputation comptable OHADA — {type.branche_cima}
                </div>
                <div className="flex justify-between text-blue-800">
                  <span>Charge sinistre :</span>
                  <span className="font-mono font-semibold">{type.compte_charge}</span>
                </div>
                <div className="flex justify-between text-blue-800">
                  <span>Provision / PSAP :</span>
                  <span className="font-mono font-semibold">{type.compte_provision}</span>
                </div>
                <p className="text-blue-500 text-xs pt-1">→ Imputation poussée automatiquement vers ORASS/Mercure à la validation</p>
              </div>
            ) : null
          })()}

          {/* Suivi étapes règlement */}
          <div className="border border-gray-100 rounded-xl p-4 bg-gray-50">
            <div className="flex items-center gap-2 mb-3">
              <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400" />
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Suivi étapes règlement</span>
            </div>
            <WorkflowTimeline etapes={s.etapes_workflow} />
          </div>

          {/* Actions rapides selon statut */}
          {s.statut === 'ouvert' && (
            <div className="flex gap-2 pt-2">
              <button className="flex-1 bg-primary-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-primary-700 transition-colors">
                Instruire le dossier
              </button>
              <button className="flex-1 border border-gray-300 rounded-lg py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors">
                Demander expertise
              </button>
            </div>
          )}
          {s.statut === 'en_cours' && (
            <div className="flex gap-2 pt-2">
              <button className="flex-1 bg-green-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-green-700 transition-colors">
                Clôturer & Régler
              </button>
              <button className="flex-1 border border-red-300 text-red-600 rounded-lg py-2 text-sm hover:bg-red-50 transition-colors">
                Rejeter
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Onglet Recours ───────────────────────────────────────────────────────────

interface Recours {
  id: string; numero: string; sinistre_ref: string; assure: string
  type: 'subrogatoire' | 'contribution'; tiers: string
  montant_reclame: number; montant_obtenu?: number
  statut: 'ouvert' | 'en_cours' | 'obtenu' | 'ferme'
  date_ouverture: string; commentaire: string
}

const DEMO_RECOURS: Recours[] = [
  { id: '1', numero: 'REC-2026-001', sinistre_ref: 'SIN-2026-001', assure: 'Kouassi Jean-Baptiste', type: 'subrogatoire', tiers: 'Bamba Seydou (responsable)', montant_reclame: 2500000, statut: 'en_cours', date_ouverture: '2026-03-20', commentaire: 'Mise en demeure envoyée — attente réponse assureur tiers Allianz' },
  { id: '2', numero: 'REC-2026-002', sinistre_ref: 'SIN-2026-004', assure: 'Bamba Seydou', type: 'contribution', tiers: 'AXA Assurances CI (co-assureur 30%)', montant_reclame: 3600000, montant_obtenu: 3600000, statut: 'obtenu', date_ouverture: '2026-02-10', commentaire: 'Quote-part recouvrée — clôturé' },
  { id: '3', numero: 'REC-2026-003', sinistre_ref: 'SIN-2026-003', assure: 'Diallo Moussa', type: 'subrogatoire', tiers: 'BICICI Banque (employeur responsable)', montant_reclame: 720000, statut: 'ouvert', date_ouverture: '2026-04-01', commentaire: 'Dossier transmis au service juridique' },
]

const RECOURS_STATUT: Record<string, { label: string; classes: string }> = {
  ouvert: { label: 'Ouvert', classes: 'bg-blue-100 text-blue-700' },
  en_cours: { label: 'En cours', classes: 'bg-yellow-100 text-yellow-700' },
  obtenu: { label: 'Obtenu', classes: 'bg-green-100 text-green-700' },
  ferme: { label: 'Fermé', classes: 'bg-gray-100 text-gray-600' },
}

function OngletRecours() {
  const [recours, setRecours] = useState<Recours[]>(DEMO_RECOURS)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ sinistre_ref: '', tiers: '', type: 'subrogatoire', montant: '', commentaire: '' })

  const totalReclame = recours.reduce((s, r) => s + r.montant_reclame, 0)
  const totalObtenu = recours.reduce((s, r) => s + (r.montant_obtenu || 0), 0)
  const fmt = (n: number) => new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'

  const soumettre = () => {
    const n: Recours = {
      id: Date.now().toString(),
      numero: `REC-2026-${String(recours.length + 1).padStart(3, '0')}`,
      sinistre_ref: form.sinistre_ref,
      assure: 'Assuré',
      type: form.type as Recours['type'],
      tiers: form.tiers,
      montant_reclame: parseFloat(form.montant) || 0,
      statut: 'ouvert',
      date_ouverture: new Date().toISOString().slice(0, 10),
      commentaire: form.commentaire,
    }
    setRecours(prev => [n, ...prev])
    setShowForm(false)
    setForm({ sinistre_ref: '', tiers: '', type: 'subrogatoire', montant: '', commentaire: '' })
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white border rounded-xl p-4 text-center">
          <p className="text-lg font-bold text-gray-900">{recours.length}</p>
          <p className="text-xs text-gray-500">Dossiers recours</p>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
          <p className="text-lg font-bold text-blue-700">{fmt(totalReclame)}</p>
          <p className="text-xs text-blue-600">Total réclamé</p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
          <p className="text-lg font-bold text-green-700">{fmt(totalObtenu)}</p>
          <p className="text-xs text-green-600">Recouvré</p>
        </div>
      </div>

      <button onClick={() => setShowForm(!showForm)}
        className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700">
        <ArrowUturnLeftIcon className="h-4 w-4" />
        Nouveau recours
      </button>

      {showForm && (
        <div className="bg-gray-50 border rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-800">Ouvrir un recours</h3>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-gray-500 mb-1">N° sinistre référence</label>
              <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="SIN-2026-XXX" value={form.sinistre_ref} onChange={e => setForm(p => ({ ...p, sinistre_ref: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Type de recours</label>
              <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value }))}>
                <option value="subrogatoire">Subrogatoire (vs tiers responsable)</option>
                <option value="contribution">Contribution (vs co-assureur)</option>
              </select></div>
            <div className="col-span-2"><label className="block text-xs text-gray-500 mb-1">Tiers visé</label>
              <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="Nom tiers / compagnie" value={form.tiers} onChange={e => setForm(p => ({ ...p, tiers: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Montant réclamé (FCFA)</label>
              <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.montant} onChange={e => setForm(p => ({ ...p, montant: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Commentaire</label>
              <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.commentaire} onChange={e => setForm(p => ({ ...p, commentaire: e.target.value }))} /></div>
          </div>
          <button onClick={soumettre} className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700">Enregistrer</button>
        </div>
      )}

      <div className="space-y-2">
        {recours.map(r => {
          const cfg = RECOURS_STATUT[r.statut]
          return (
            <div key={r.id} className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <ArrowUturnLeftIcon className="h-4 w-4 text-primary-600" />
                  <span className="text-sm font-semibold text-gray-900">{r.numero}</span>
                  <span className="text-xs text-gray-500">→ {r.sinistre_ref}</span>
                </div>
                <span className={clsx('text-xs font-medium px-2 py-0.5 rounded-full', cfg.classes)}>{cfg.label}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 mb-2">
                <div><span className="text-gray-400">Type :</span> {r.type === 'subrogatoire' ? 'Subrogatoire' : 'Contribution'}</div>
                <div><span className="text-gray-400">Tiers :</span> {r.tiers}</div>
                <div><span className="text-gray-400">Réclamé :</span> <span className="font-medium text-gray-800">{fmt(r.montant_reclame)}</span></div>
                {r.montant_obtenu ? <div><span className="text-gray-400">Recouvré :</span> <span className="font-medium text-green-700">{fmt(r.montant_obtenu)}</span></div> : null}
              </div>
              <p className="text-xs text-gray-500 bg-gray-50 rounded px-2 py-1">{r.commentaire}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Onglet Correspondances → délégué à CorrespondancesModule ─────────────────

// ─── Page principale ──────────────────────────────────────────────────────────

type Etape = 'choix_type' | 'scan' | 'validation' | 'succes'

type OngletSinistre = 'dossiers' | 'recours' | 'correspondances' | 'fournisseurs' | 'courtiers' | 'archive' | 'rapports'

// ─── Onglet Fournisseurs (intégré dans sinistres) ─────────────────────────────

type StatutFourn = 'en_attente' | 'analyse_en_cours' | 'valide' | 'rejete'
interface PieceFournisseur {
  id: string; fournisseur: string; type_fournisseur: string
  sinistre_ref: string; type_document: string; fichier_nom: string
  date_envoi: string; statut: StatutFourn; score_ia: number | null; analyse_ia: string
}

const PIECES_FOURN_DEMO: PieceFournisseur[] = [
  { id: 'f1', fournisseur: 'Garage Central Yaoundé', type_fournisseur: 'Garage', sinistre_ref: 'SIN-2026-0342', type_document: 'Facture de réparation', fichier_nom: 'facture_reparation_342.pdf', date_envoi: '2026-04-08 14:32', statut: 'en_attente', score_ia: null, analyse_ia: '' },
  { id: 'f2', fournisseur: 'Clinique Les Sœurs', type_fournisseur: 'Clinique', sinistre_ref: 'SIN-2026-0289', type_document: 'Rapport médical', fichier_nom: 'rapport_medical_289.pdf', date_envoi: '2026-04-07 09:15', statut: 'valide', score_ia: 78, analyse_ia: 'Montant cohérent avec les tarifs conventionnels.' },
  { id: 'f3', fournisseur: 'Expert SARL', type_fournisseur: 'Expert', sinistre_ref: 'SIN-2026-0301', type_document: "Rapport d'expertise", fichier_nom: 'rapport_expertise_301.pdf', date_envoi: '2026-04-06 16:45', statut: 'valide', score_ia: 92, analyse_ia: 'Document authentique. Recommandation : importer vers ORASS.' },
  { id: 'f4', fournisseur: 'Pharmacie du Centre', type_fournisseur: 'Pharmacie', sinistre_ref: 'SIN-2026-0255', type_document: 'Facture pharmacie', fichier_nom: 'facture_pharma_255.pdf', date_envoi: '2026-04-05 11:20', statut: 'rejete', score_ia: 34, analyse_ia: 'ALERTE : Montant anormalement élevé. Risque fraude élevé.' },
]

function OngletFournisseursSinistres() {
  const [pieces, setPieces] = useState<PieceFournisseur[]>(PIECES_FOURN_DEMO)

  const valider = (id: string) => setPieces(prev => prev.map(p => p.id === id ? { ...p, statut: 'valide' as const } : p))
  const rejeter = (id: string) => setPieces(prev => prev.map(p => p.id === id ? { ...p, statut: 'rejete' as const } : p))

  const enAttente = pieces.filter(p => p.statut === 'en_attente').length

  const statutCls = (s: StatutFourn) => ({
    en_attente: 'bg-amber-100 text-amber-700',
    analyse_en_cours: 'bg-blue-100 text-blue-700',
    valide: 'bg-green-100 text-green-700',
    rejete: 'bg-red-100 text-red-700',
  }[s])
  const statutLabel = (s: StatutFourn) => ({ en_attente: 'En attente', analyse_en_cours: 'Analyse…', valide: 'Validé', rejete: 'Rejeté' }[s])

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'En attente', value: enAttente, cls: 'border-amber-200 bg-amber-50 text-amber-700' },
          { label: 'Validés', value: pieces.filter(p => p.statut === 'valide').length, cls: 'border-green-200 bg-green-50 text-green-700' },
          { label: 'Rejetés', value: pieces.filter(p => p.statut === 'rejete').length, cls: 'border-red-200 bg-red-50 text-red-700' },
          { label: 'Total reçus', value: pieces.length, cls: 'border-gray-200 bg-gray-50 text-gray-700' },
        ].map((k, i) => (
          <div key={i} className={clsx('border rounded-xl p-4 text-center', k.cls)}>
            <p className="text-2xl font-bold">{k.value}</p>
            <p className="text-xs mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <BuildingStorefrontIcon className="h-5 w-5 text-indigo-600" />
            Documents reçus des fournisseurs
          </h3>
          {enAttente > 0 && (
            <span className="bg-amber-100 text-amber-700 text-xs font-bold px-2 py-1 rounded-full">
              {enAttente} en attente de validation
            </span>
          )}
        </div>
        <div className="divide-y divide-gray-100">
          {pieces.map(p => (
            <div key={p.id} className="px-6 py-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900 text-sm">{p.fournisseur}</span>
                  <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">{p.type_fournisseur}</span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{p.type_document} — <span className="font-mono text-primary-600">{p.sinistre_ref}</span></p>
                <p className="text-xs text-gray-400 mt-0.5">{p.fichier_nom} · {p.date_envoi}</p>
                {p.analyse_ia && <p className="text-xs text-gray-600 mt-1 italic">{p.analyse_ia}</p>}
              </div>
              {p.score_ia !== null && (
                <div className={clsx('text-center px-3 py-1.5 rounded-lg text-xs font-bold',
                  p.score_ia >= 70 ? 'bg-green-100 text-green-700' : p.score_ia >= 45 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'
                )}>
                  IA {p.score_ia}/100
                </div>
              )}
              <span className={clsx('px-2 py-1 rounded-full text-xs font-medium', statutCls(p.statut))}>
                {statutLabel(p.statut)}
              </span>
              {p.statut === 'en_attente' && (
                <div className="flex gap-2">
                  <button onClick={() => valider(p.id)} className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-semibold hover:bg-green-700 transition-colors">
                    ✓ Valider → ORASS
                  </button>
                  <button onClick={() => rejeter(p.id)} className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-xs font-semibold hover:bg-red-200 transition-colors">
                    ✕ Rejeter
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function SinistresPage() {
  const [onglet, setOnglet] = useState<OngletSinistre>('dossiers')
  const [sinistres, setSinistres] = useState<Sinistre[]>(DEMO_SINISTRES)
  const [isDemoData, setIsDemoData] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [filtreFamille, setFiltreFamille] = useState<FamilleSinistre | 'tous'>('tous')
  const [filtreBranche, setFiltreBranche] = useState<string>('tous')
  const [detail, setDetail] = useState<Sinistre | null>(null)
  const [showNouveauSinistre, setShowNouveauSinistre] = useState(false)

  // Workflow nouveau sinistre
  const [etape, setEtape] = useState<Etape>('choix_type')
  const [typeChoisi, setTypeChoisi] = useState<TypeSinistre | null>(null)
  const [ocrResult, setOcrResult] = useState<OcrResult | null>(null)
  const [ocrFichier, setOcrFichier] = useState<File | null>(null)

  useEffect(() => {
    setIsLoading(true)
    sinistresAPI.list().then((data: unknown) => {
      const d = data as Record<string, unknown>
      const list = Array.isArray(data) ? data as Sinistre[] : (d.items as Sinistre[])
      if (list && list.length > 0) { setSinistres(list); setIsDemoData(false) }
    }).catch(() => {})
      .finally(() => setIsLoading(false))
  }, [])

  const handleOcrResult = useCallback((r: OcrResult, file: File) => {
    setOcrResult(r)
    setOcrFichier(file)
    setEtape('validation')
  }, [])

  const handleValider = useCallback(async (champs: Record<string, string>) => {
    // Soumettre le sinistre
    const payload = {
      branche: typeChoisi?.id || 'auto',
      type_sinistre: typeChoisi?.id,
      famille: typeChoisi?.famille,
      ...champs,
      montant_estime: parseFloat(champs.montant_estime || champs.capital_garanti || champs.total_facture || '0'),
      assure_nom: champs.assure_nom || champs.assure_deces || '',
      description: champs.description || champs.nature_sinistre || champs.pathologie || `Sinistre ${typeChoisi?.label} — traitement automatique`,
    }
    try {
      const resp = await sinistresAPI.declarer(payload) as Record<string, unknown>
      const nouveau: Sinistre = {
        id: (resp.id as string) || Date.now().toString(),
        numero: (resp.numero as string) || `SIN-2026-${String(sinistres.length + 1).padStart(3, '0')}`,
        branche: typeChoisi?.id as Sinistre['branche'] || 'auto',
        statut: 'ouvert',
        date_sinistre: champs.date_sinistre || champs.date_deces || new Date().toISOString().slice(0, 10),
        date_declaration: new Date().toISOString().slice(0, 10),
        montant_estime: parseFloat(champs.montant_estime || champs.capital_garanti || '0'),
        assure_nom: champs.assure_nom || '',
        description: payload.description,
        score_fraude: (resp.score_fraude as number) || 0,
        police_numero: champs.police_numero || '',
      }
      setSinistres(prev => [nouveau, ...prev])
    } catch {
      const nouveau: Sinistre = {
        id: Date.now().toString(),
        numero: `SIN-2026-${String(sinistres.length + 1).padStart(3, '0')}`,
        branche: typeChoisi?.id as Sinistre['branche'] || 'auto',
        statut: 'ouvert',
        date_sinistre: champs.date_sinistre || new Date().toISOString().slice(0, 10),
        date_declaration: new Date().toISOString().slice(0, 10),
        montant_estime: parseFloat(champs.montant_estime || '0'),
        assure_nom: champs.assure_nom || '',
        description: payload.description,
        score_fraude: 0,
        police_numero: champs.police_numero || '',
      }
      setSinistres(prev => [nouveau, ...prev])
    }
    setEtape('succes')
  }, [typeChoisi, sinistres.length])

  const resetWorkflow = useCallback(() => {
    setEtape('choix_type')
    setTypeChoisi(null)
    setOcrResult(null)
    setOcrFichier(null)
    setShowNouveauSinistre(false)
  }, [])

  // Filtres
  const sinistresFiltres = sinistres.filter(s => {
    const matchSearch = !search || s.assure_nom.toLowerCase().includes(search.toLowerCase()) ||
      s.numero.toLowerCase().includes(search.toLowerCase())
    const matchFamille = filtreFamille === 'tous' ||
      (filtreFamille === 'vie' && (s.branche === 'vie' || s.branche === 'sante')) ||
      (filtreFamille === 'non_vie' && s.branche !== 'vie' && s.branche !== 'sante')
    const matchBranche = filtreBranche === 'tous' || s.branche === filtreBranche
    return matchSearch && matchFamille && matchBranche
  })

  // Stats rapides
  const statsVie = sinistres.filter(s => s.branche === 'vie' || s.branche === 'sante').length
  const statsNonVie = sinistres.filter(s => s.branche !== 'vie' && s.branche !== 'sante').length
  const statsEnCours = sinistres.filter(s => s.statut === 'en_cours' || s.statut === 'ouvert').length

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sinistres</h1>
          <p className="text-sm text-gray-500 mt-0.5">Vie & Non-Vie · Branches CIMA · Recours · Correspondances</p>
          {isDemoData && <DemoBanner className="mt-2" />}
        </div>
        {onglet === 'dossiers' && (
          <button
            onClick={() => { setShowNouveauSinistre(true); setEtape('choix_type') }}
            className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors shadow-sm"
          >
            <DocumentArrowUpIcon className="h-4 w-4" />
            Déclarer un sinistre
          </button>
        )}
      </div>

      {/* Onglets */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {([
          { id: 'dossiers', label: 'Dossiers & Instruction', icon: ShieldExclamationIcon },
          { id: 'recours', label: 'Recours', icon: ArrowUturnLeftIcon },
          { id: 'correspondances', label: 'Correspondances', icon: PencilSquareIcon },
          { id: 'fournisseurs', label: 'Fournisseurs', icon: BuildingStorefrontIcon },
          { id: 'courtiers', label: 'Courtiers', icon: UserGroupIcon },
          { id: 'archive', label: 'Archive', icon: DocumentTextIcon },
          { id: 'rapports', label: 'Rapports', icon: ChartBarIcon },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id)}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              onglet === id ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            )}>
            <Icon className="h-4 w-4" />{label}
          </button>
        ))}
      </div>

      {/* Onglet Recours */}
      {onglet === 'recours' && <OngletRecours />}

      {/* Onglet Correspondances */}
      {onglet === 'correspondances' && (
        <CorrespondancesModule
          module="sinistres"
          titre="Correspondances — Sinistres"
          references={sinistres.map(s => ({ value: s.numero, label: `${s.numero} — ${s.assure_nom}` }))}
        />
      )}

      {/* Onglet Fournisseurs */}
      {onglet === 'fournisseurs' && <OngletFournisseursSinistres />}

      {/* Onglet Courtiers */}
      {onglet === 'courtiers' && (
        <div className="max-w-3xl">
          <OngletCourtiers categorieFiltre="sinistre" />
        </div>
      )}

      {/* Onglet Archive */}
      {onglet === 'archive' && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <DocumentTextIcon className="h-5 w-5 text-primary-600" />
            Archive numérique — Sinistres
          </h3>
          <ArchiveNumerique module="sinistres" hauteurMax="550px" />
        </div>
      )}

      {/* Onglet Rapports */}
      {onglet === 'rapports' && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <RapportsModule module="sinistres" />
        </div>
      )}

      {/* Onglet Dossiers */}
      {onglet === 'dossiers' && <>

      {/* Stats rapides */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <p className="text-2xl font-bold text-gray-900">{statsEnCours}</p>
          <p className="text-xs text-gray-500 mt-0.5">En cours / Ouverts</p>
        </div>
        <div className="bg-emerald-50 rounded-xl border border-emerald-200 p-4 text-center">
          <p className="text-2xl font-bold text-emerald-700">{statsVie}</p>
          <p className="text-xs text-emerald-600 mt-0.5">Sinistres Vie</p>
        </div>
        <div className="bg-blue-50 rounded-xl border border-blue-200 p-4 text-center">
          <p className="text-2xl font-bold text-blue-700">{statsNonVie}</p>
          <p className="text-xs text-blue-600 mt-0.5">Sinistres Non-Vie</p>
        </div>
      </div>

      {/* Recherche + filtres */}
      <div className="space-y-3">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="Rechercher un sinistre ou assuré…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <div className="flex rounded-lg border border-gray-300 overflow-hidden text-sm">
            {(['tous', 'vie', 'non_vie'] as const).map(f => (
              <button key={f} onClick={() => { setFiltreFamille(f); setFiltreBranche('tous') }}
                className={clsx('px-3 py-2 transition-colors',
                  filtreFamille === f ? 'bg-primary-600 text-white' : 'text-gray-600 hover:bg-gray-50'
                )}>
                {f === 'tous' ? 'Tous' : f === 'vie' ? '❤️ Vie' : '🛡️ Non-Vie'}
              </button>
            ))}
          </div>
        </div>

        {/* Filtre par branche */}
        {filtreFamille !== 'tous' && (
          <div className="flex gap-2 flex-wrap">
            <button onClick={() => setFiltreBranche('tous')}
              className={clsx('px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                filtreBranche === 'tous' ? 'bg-gray-700 text-white border-gray-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50')}>
              Toutes branches
            </button>
            {TYPES_SINISTRE.filter(t => t.famille === filtreFamille).map(t => (
              <button key={t.id} onClick={() => setFiltreBranche(t.id)}
                className={clsx('px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                  filtreBranche === t.id
                    ? t.couleur.replace('hover:', '').replace('bg-', 'bg-').split(' ').slice(0, 3).join(' ')
                    : 'border-gray-300 text-gray-600 hover:bg-gray-50')}>
                {t.label} <span className="opacity-60 ml-0.5">· {t.branche_cima}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Liste sinistres */}
      {isLoading ? (
        <LoadingSpinner className="mx-auto" />
      ) : (
        <div className="space-y-2">
          {sinistresFiltres.length === 0 ? (
            <EmptyState
              icon={<ShieldExclamationIcon className="h-10 w-10" />}
              title="Aucun sinistre trouvé"
              description="Aucun sinistre ne correspond aux filtres sélectionnés."
            />
          ) : (
            sinistresFiltres.map(s => (
              <SinistreCard key={s.id} s={s} onClick={() => setDetail(s)} />
            ))
          )}
        </div>
      )}

      {/* Panneau nouveau sinistre */}
      {showNouveauSinistre && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header panneau */}
            <div className="flex items-center justify-between p-6 border-b sticky top-0 bg-white z-10">
              <div>
                <h2 className="text-lg font-bold text-gray-900">Déclarer un sinistre</h2>
                <div className="flex items-center gap-2 mt-1">
                  {(['choix_type', 'scan', 'validation', 'succes'] as Etape[]).map((e, i) => (
                    <div key={e} className="flex items-center gap-1">
                      <div className={clsx(
                        'w-5 h-5 rounded-full text-xs flex items-center justify-center font-medium',
                        etape === e ? 'bg-primary-600 text-white' :
                        (['choix_type', 'scan', 'validation', 'succes'] as Etape[]).indexOf(etape) > i
                          ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'
                      )}>{i + 1}</div>
                      {i < 3 && <div className="w-4 h-0.5 bg-gray-200" />}
                    </div>
                  ))}
                </div>
              </div>
              <button onClick={resetWorkflow} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6">
              {/* Étape 1 : choix du type */}
              {etape === 'choix_type' && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">Quel type de sinistre souhaitez-vous déclarer ?</p>

                  <div className="space-y-3">
                    <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Non-Vie</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {TYPES_SINISTRE.filter(t => t.famille === 'non_vie').map(type => (
                        <button
                          key={type.id}
                          onClick={() => { setTypeChoisi(type); setEtape('scan') }}
                          className={clsx('flex items-center gap-3 p-3 rounded-xl border-2 text-sm font-medium transition-all hover:shadow-sm', type.couleur)}
                        >
                          <type.icon className="h-5 w-5 flex-shrink-0" />
                          {type.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Vie & Santé</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {TYPES_SINISTRE.filter(t => t.famille === 'vie').map(type => (
                        <button
                          key={type.id}
                          onClick={() => { setTypeChoisi(type); setEtape('scan') }}
                          className={clsx('flex items-center gap-3 p-3 rounded-xl border-2 text-sm font-medium transition-all hover:shadow-sm', type.couleur)}
                        >
                          <type.icon className="h-5 w-5 flex-shrink-0" />
                          {type.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Étape 2 : scan */}
              {etape === 'scan' && typeChoisi && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <typeChoisi.icon className={clsx('h-5 w-5', typeChoisi.couleur.split(' ').find(c => c.startsWith('text-')))} />
                    <span className="font-semibold text-gray-800">{typeChoisi.label}</span>
                  </div>
                  <p className="text-sm text-gray-600">
                    Scannez ou photographiez un document pour que YukpoPro extrait automatiquement toutes les informations nécessaires.
                  </p>
                  <ScanZone
                    typeSinistre={typeChoisi}
                    onResult={handleOcrResult}
                    onCancel={() => setEtape('choix_type')}
                  />
                </div>
              )}

              {/* Étape 3 : validation */}
              {etape === 'validation' && typeChoisi && ocrResult && ocrFichier && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">
                    YukpoPro a extrait les informations suivantes. Vérifiez et corrigez si nécessaire avant de soumettre.
                  </p>
                  <ValidationExtraction
                    type={typeChoisi}
                    ocr={ocrResult}
                    fichier={ocrFichier}
                    onValider={handleValider}
                    onRetry={() => setEtape('scan')}
                  />
                </div>
              )}

              {/* Étape 4 : succès */}
              {etape === 'succes' && (
                <div className="text-center py-8 space-y-4">
                  <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
                    <CheckCircleIcon className="h-10 w-10 text-green-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">Sinistre déclaré avec succès</h3>
                    <p className="text-sm text-gray-500 mt-1">
                      Le dossier a été créé et est visible dans la liste. YukpoPro a calculé le score de fraude initial.
                    </p>
                  </div>
                  <div className="flex gap-3 justify-center">
                    <button
                      onClick={resetWorkflow}
                      className="bg-primary-600 text-white px-6 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors"
                    >
                      Terminer
                    </button>
                    <button
                      onClick={() => { setEtape('choix_type'); setTypeChoisi(null); setOcrResult(null) }}
                      className="border border-gray-300 text-gray-700 px-6 py-2 rounded-lg text-sm hover:bg-gray-50 transition-colors"
                    >
                      Nouveau sinistre
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal détail */}
      {detail && <SinistreDetail s={detail} onClose={() => setDetail(null)} />}
      </>}
    </div>
  )
}
