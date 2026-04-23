import { useState } from 'react'
import {
  MagnifyingGlassIcon, PlusIcon, ChartBarIcon, UserGroupIcon,
  DocumentTextIcon, SparklesIcon, ArrowRightIcon, PhoneIcon,
  EnvelopeIcon, CalendarIcon, CheckCircleIcon, XMarkIcon,
  ArrowTrendingUpIcon, BanknotesIcon, ClipboardDocumentCheckIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { apiClient } from '../api/client'
import { RapportsModule } from '../components/RapportsModule'
import { DemoBanner } from '../components/DemoBanner'
import { EmptyState } from '../components/EmptyState'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Prospect {
  id: string; nom: string; telephone?: string; email?: string
  branche_interet: string; famille: 'vie' | 'non_vie'
  etape: 'lead' | 'contact' | 'proposition' | 'negociation' | 'gagne' | 'perdu'
  valeur_estimee: number; date_creation: string
  commercial_assigne: string; notes: string; documents_envoyes: string[]
}

const ETAPES = ['lead', 'contact', 'proposition', 'negociation', 'gagne', 'perdu'] as const

const ETAPE_CFG: Record<string, { label: string; couleur: string; bg: string }> = {
  lead:        { label: 'Lead', couleur: 'text-gray-600', bg: 'bg-gray-100' },
  contact:     { label: 'Contact établi', couleur: 'text-blue-600', bg: 'bg-blue-100' },
  proposition: { label: 'Proposition', couleur: 'text-indigo-600', bg: 'bg-indigo-100' },
  negociation: { label: 'Négociation', couleur: 'text-amber-600', bg: 'bg-amber-100' },
  gagne:       { label: 'Gagné ✓', couleur: 'text-green-600', bg: 'bg-green-100' },
  perdu:       { label: 'Perdu', couleur: 'text-red-600', bg: 'bg-red-100' },
}

const PRODUITS_PROSPECTION = [
  { value: 'auto', label: 'Automobile RC', famille: 'non_vie' },
  { value: 'mrh', label: 'MRH Habitation', famille: 'non_vie' },
  { value: 'transport', label: 'Transport / CMR', famille: 'non_vie' },
  { value: 'rc', label: 'RC Entreprise', famille: 'non_vie' },
  { value: 'vie_entiere', label: 'Vie Entière', famille: 'vie' },
  { value: 'credit_vie', label: 'Crédit-Vie', famille: 'vie' },
  { value: 'vie_mixte', label: 'Vie Mixte / Épargne', famille: 'vie' },
  { value: 'prevoyance', label: 'Prévoyance / ITT', famille: 'vie' },
  { value: 'education', label: 'Éducation Enfant', famille: 'vie' },
  { value: 'retraite', label: 'Retraite', famille: 'vie' },
]

const COMMERCIAUX = ['A. Koffi', 'M. Sanogo', 'I. Diallo', 'F. Traoré', 'P. Nkeng']

const DEMO_PROSPECTS: Prospect[] = [
  { id: '1', nom: 'Entreprise SODECI', telephone: '+225 07 00 00 01', email: 'dg@sodeci.ci', branche_interet: 'rc', famille: 'non_vie', etape: 'negociation', valeur_estimee: 8_500_000, date_creation: '2026-01-10', commercial_assigne: 'A. Koffi', notes: 'DG très intéressé — réunion de closing la semaine prochaine', documents_envoyes: ['Devis RC Entreprise', 'Plaquette produits'] },
  { id: '2', nom: 'Famille Ouattara', telephone: '+225 05 00 00 02', branche_interet: 'mrh', famille: 'non_vie', etape: 'proposition', valeur_estimee: 450_000, date_creation: '2026-01-15', commercial_assigne: 'M. Sanogo', notes: 'Bien villa de 200m² à Cocody', documents_envoyes: ['Devis MRH Villa'] },
  { id: '3', nom: 'Transport Bakayoko SARL', telephone: '+225 01 02 03 04', branche_interet: 'transport', famille: 'non_vie', etape: 'gagne', valeur_estimee: 3_200_000, date_creation: '2025-12-20', commercial_assigne: 'A. Koffi', notes: 'Contrat signé — souscription en cours', documents_envoyes: ['Proposition transport', 'Conditions particulières'] },
  { id: '4', nom: 'Dr. Koné Fatou', telephone: '+225 07 88 00 22', branche_interet: 'vie_mixte', famille: 'vie', etape: 'contact', valeur_estimee: 720_000, date_creation: '2026-02-01', commercial_assigne: 'I. Diallo', notes: 'Médecin libéral — très intéressée par épargne vie mixte', documents_envoyes: [] },
  { id: '5', nom: 'Agence Immobilière Lumière', branche_interet: 'mrh', famille: 'non_vie', etape: 'lead', valeur_estimee: 1_200_000, date_creation: '2026-02-05', commercial_assigne: 'M. Sanogo', notes: '', documents_envoyes: [] },
  { id: '6', nom: 'M. Coulibaly Jean', telephone: '+225 07 11 22 33', branche_interet: 'prevoyance', famille: 'vie', etape: 'proposition', valeur_estimee: 380_000, date_creation: '2026-01-25', commercial_assigne: 'I. Diallo', notes: 'Fonctionnaire — intéressé prévoyance ITT', documents_envoyes: ['Devis Prévoyance ITT'] },
  { id: '7', nom: 'SARL Bâtisseurs Plus', telephone: '+225 27 00 11 22', branche_interet: 'rc', famille: 'non_vie', etape: 'perdu', valeur_estimee: 2_100_000, date_creation: '2025-11-01', commercial_assigne: 'F. Traoré', notes: 'Parti à la concurrence — tarif trop élevé', documents_envoyes: ['Devis RC BTP'] },
  { id: '8', nom: 'M. Touré Lamine', telephone: '+225 05 44 33 22', branche_interet: 'retraite', famille: 'vie', etape: 'negociation', valeur_estimee: 960_000, date_creation: '2026-03-01', commercial_assigne: 'P. Nkeng', notes: 'Cadre supérieur — départ retraite dans 15 ans', documents_envoyes: ['Simulation retraite', 'Plaquette épargne'] },
]

// ─── Kanban ───────────────────────────────────────────────────────────────────

function KanbanColumn({ etape, prospects, onSelect }: { etape: string; prospects: Prospect[]; onSelect: (p: Prospect) => void }) {
  const total = prospects.reduce((s, p) => s + p.valeur_estimee, 0)
  const cfg = ETAPE_CFG[etape]
  const fmt = (v: number) => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : `${(v / 1_000).toFixed(0)}K`

  return (
    <div className="flex flex-col min-w-52 bg-gray-50 rounded-xl border border-gray-200 p-3">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-xs font-semibold text-gray-700">{cfg.label}</p>
          <p className="text-xs text-gray-400">{prospects.length} · {fmt(total)} FCFA</p>
        </div>
        <span className={clsx('text-xs font-bold px-2 py-0.5 rounded-full', cfg.bg, cfg.couleur)}>
          {prospects.length}
        </span>
      </div>
      <div className="space-y-2 flex-1">
        {prospects.map(p => (
          <div key={p.id} onClick={() => onSelect(p)}
            className={clsx('bg-white rounded-lg border p-3 shadow-sm hover:shadow-md transition-shadow cursor-pointer',
              p.famille === 'vie' ? 'border-l-2 border-l-rose-400' : 'border-l-2 border-l-blue-400'
            )}>
            <p className="text-xs font-semibold text-gray-800 line-clamp-1">{p.nom}</p>
            <div className="flex items-center justify-between mt-1.5">
              <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium',
                p.famille === 'vie' ? 'bg-rose-50 text-rose-700' : 'bg-blue-50 text-blue-700')}>
                {PRODUITS_PROSPECTION.find(pp => pp.value === p.branche_interet)?.label || p.branche_interet}
              </span>
              <span className="text-xs font-medium text-primary-600">{fmt(p.valeur_estimee)}</span>
            </div>
            <p className="text-xs text-gray-400 mt-1 truncate">→ {p.commercial_assigne}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Détail prospect + actions ────────────────────────────────────────────────

function ProspectDetail({ p, onClose, onUpdate }: { p: Prospect; onClose: () => void; onUpdate: (p: Prospect) => void }) {
  const [devisLoading, setDevisLoading] = useState(false)
  const [devis, setDevis] = useState('')
  const [etapeEdit, setEtapeEdit] = useState(p.etape)

  const genererDevis = async () => {
    setDevisLoading(true)
    const produit = PRODUITS_PROSPECTION.find(pp => pp.value === p.branche_interet)
    try {
      const { data } = await apiClient.post('/api/v1/chat/message', {
        message: `Génère une proposition commerciale professionnelle pour ${p.nom} (${p.telephone || p.email || 'contact N/A'}) intéressé(e) par ${produit?.label}. Valeur estimée : ${p.valeur_estimee.toLocaleString('fr-FR')} FCFA. Notes : ${p.notes || 'aucune'}. Format : document de présentation avec description du produit, avantages, tarification indicative, appel à l'action. Style professionnel CIMA zone Afrique de l'Ouest.`,
        stream: false,
      })
      const d = data as Record<string, unknown>
      setDevis((d.response as string) || (d.content as string) || '')
    } catch {
      const produitLabel = produit?.label || p.branche_interet
      setDevis(`PROPOSITION COMMERCIALE\n━━━━━━━━━━━━━━━━━━━━━━━━\n\nÀ l'attention de : ${p.nom}\nProduit : ${produitLabel}\nCommercial : ${p.commercial_assigne}\nDate : ${new Date().toLocaleDateString('fr-FR')}\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n\nCher(e) ${p.nom},\n\nSuite à notre entretien, nous avons le plaisir de vous soumettre notre proposition pour ${produitLabel}.\n\nOBJECTIF DU CONTRAT\n• Protection : couverture adaptée à votre situation\n• Sécurité : capital garanti selon barèmes CIMA\n• Épargne : constitution progressive de capital\n\nPRIME INDICATIVE\n• Prime annuelle estimée : ${p.valeur_estimee.toLocaleString('fr-FR')} FCFA\n• Durée recommandée : selon votre profil\n• Modalité : annuelle, semestrielle ou mensuelle\n\nAVANTAGES\n✓ Couverture immédiate à la souscription\n✓ Assistance 24h/7j\n✓ Règlement rapide des sinistres\n✓ Conformité Code CIMA\n\nNous restons disponibles pour tout complément d'information.\n\nCordialement,\n${p.commercial_assigne}\nConseiller Commercial`)
    } finally { setDevisLoading(false) }
  }

  const avancer = () => {
    const idx = ETAPES.indexOf(etapeEdit)
    if (idx < ETAPES.length - 2) {
      const nouvelle = ETAPES[idx + 1]
      setEtapeEdit(nouvelle)
      onUpdate({ ...p, etape: nouvelle })
    }
  }

  const fmt = (v: number) => new Intl.NumberFormat('fr-FR').format(v) + ' FCFA'

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b sticky top-0 bg-white">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{p.nom}</h2>
            <p className="text-sm text-gray-500">{PRODUITS_PROSPECTION.find(pp => pp.value === p.branche_interet)?.label} · {p.commercial_assigne}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Infos */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            {p.telephone && <div className="flex items-center gap-2"><PhoneIcon className="h-4 w-4 text-gray-400" /><span>{p.telephone}</span></div>}
            {p.email && <div className="flex items-center gap-2"><EnvelopeIcon className="h-4 w-4 text-gray-400" /><span>{p.email}</span></div>}
            <div className="flex items-center gap-2"><BanknotesIcon className="h-4 w-4 text-gray-400" /><span className="font-medium">{fmt(p.valeur_estimee)}</span></div>
            <div className="flex items-center gap-2"><CalendarIcon className="h-4 w-4 text-gray-400" /><span>{p.date_creation}</span></div>
          </div>

          {/* Statut pipeline */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-2">Étape pipeline</label>
            <div className="flex gap-1 flex-wrap">
              {ETAPES.map(e => (
                <button key={e} onClick={() => { setEtapeEdit(e); onUpdate({ ...p, etape: e }) }}
                  className={clsx('px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
                    etapeEdit === e ? clsx(ETAPE_CFG[e].bg, ETAPE_CFG[e].couleur, 'ring-2 ring-current') :
                    'bg-gray-100 text-gray-500 hover:bg-gray-200')}>
                  {ETAPE_CFG[e].label}
                </button>
              ))}
            </div>
          </div>

          {p.notes && (
            <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-sm text-amber-800">
              <p className="text-xs font-semibold text-amber-600 mb-1">Notes commerciales</p>
              {p.notes}
            </div>
          )}

          {p.documents_envoyes.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-600 mb-2">Documents envoyés</p>
              <div className="flex gap-2 flex-wrap">
                {p.documents_envoyes.map((d, i) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">{d}</span>
                ))}
              </div>
            </div>
          )}

          {/* Génération devis */}
          <div className="border-t pt-4 space-y-3">
            <button onClick={genererDevis} disabled={devisLoading}
              className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 disabled:opacity-60">
              <SparklesIcon className="h-4 w-4" />
              {devisLoading ? 'Génération en cours…' : 'Générer une proposition commerciale IA'}
            </button>

            {devis && (
              <div className="space-y-2">
                <textarea className="w-full border border-gray-300 rounded-xl p-4 text-sm font-mono h-64 resize-none focus:ring-2 focus:ring-primary-500"
                  value={devis} onChange={e => setDevis(e.target.value)} />
                <div className="flex gap-2">
                  <button onClick={() => navigator.clipboard?.writeText(devis)}
                    className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50">
                    Copier
                  </button>
                  <button className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50">
                    Envoyer par email
                  </button>
                  {etapeEdit !== 'gagne' && etapeEdit !== 'perdu' && (
                    <button onClick={avancer}
                      className="flex-1 bg-green-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-green-700">
                      Avancer pipeline
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Lien souscription */}
          {etapeEdit === 'gagne' && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-green-800">Prospect gagné !</p>
                <p className="text-xs text-green-600">Initier la souscription depuis ce dossier</p>
              </div>
              <a href="/souscription"
                className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-green-700">
                <ClipboardDocumentCheckIcon className="h-4 w-4" />
                Souscrire
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Onglet Performances ──────────────────────────────────────────────────────

function OngletPerformances({ prospects }: { prospects: Prospect[] }) {
  const fmt = (v: number) => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)} M` : `${(v / 1_000).toFixed(0)} K`
  const total = prospects.reduce((s, p) => s + p.valeur_estimee, 0)
  const gagnes = prospects.filter(p => p.etape === 'gagne')
  const pipeline = prospects.filter(p => !['gagne', 'perdu'].includes(p.etape))
  const tauxConversion = prospects.length > 0 ? Math.round((gagnes.length / prospects.length) * 100) : 0

  const parCommercial = COMMERCIAUX.map(c => {
    const pp = prospects.filter(p => p.commercial_assigne === c)
    const gg = pp.filter(p => p.etape === 'gagne')
    return {
      nom: c, total: pp.length, gagnes: gg.length, ca: gg.reduce((s, p) => s + p.valeur_estimee, 0),
      taux: pp.length > 0 ? Math.round((gg.length / pp.length) * 100) : 0,
    }
  }).filter(c => c.total > 0).sort((a, b) => b.ca - a.ca)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Pipeline total', value: `${fmt(total)} FCFA`, sub: `${pipeline.length} prospects actifs`, color: 'text-primary-700' },
          { label: 'CA généré (gagné)', value: `${fmt(gagnes.reduce((s, p) => s + p.valeur_estimee, 0))} FCFA`, sub: `${gagnes.length} contrats`, color: 'text-green-700' },
          { label: 'Taux de conversion', value: `${tauxConversion}%`, sub: 'global tous commerciaux', color: tauxConversion > 30 ? 'text-green-700' : 'text-amber-700' },
          { label: 'Vie vs Non-Vie', value: `${prospects.filter(p => p.famille === 'vie').length}/${prospects.filter(p => p.famille === 'non_vie').length}`, sub: 'Vie / Non-Vie', color: 'text-indigo-700' },
        ].map(kpi => (
          <div key={kpi.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-500">{kpi.label}</p>
            <p className={clsx('text-xl font-bold mt-1', kpi.color)}>{kpi.value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{kpi.sub}</p>
          </div>
        ))}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b bg-gray-50">
          <h3 className="text-sm font-semibold text-gray-800">Performance par commercial</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 bg-gray-50 border-b">
              <th className="text-left px-4 py-2">Commercial</th>
              <th className="text-right px-4 py-2">Prospects</th>
              <th className="text-right px-4 py-2">Gagnés</th>
              <th className="text-right px-4 py-2">Taux</th>
              <th className="text-right px-4 py-2">CA</th>
            </tr>
          </thead>
          <tbody>
            {parCommercial.map((c, i) => (
              <tr key={c.nom} className={clsx('border-b last:border-b-0', i === 0 && 'bg-amber-50')}>
                <td className="px-4 py-2.5 font-medium text-gray-800">
                  {i === 0 && <span className="mr-1">🏆</span>}{c.nom}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-600">{c.total}</td>
                <td className="px-4 py-2.5 text-right text-green-600 font-medium">{c.gagnes}</td>
                <td className="px-4 py-2.5 text-right">
                  <span className={clsx('text-xs font-semibold px-1.5 py-0.5 rounded-full',
                    c.taux > 40 ? 'bg-green-100 text-green-700' : c.taux > 20 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700')}>
                    {c.taux}%
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-semibold text-primary-700">{fmt(c.ca)} FCFA</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">Répartition par étape</h3>
        <div className="space-y-2">
          {ETAPES.filter(e => e !== 'perdu').map(e => {
            const pp = prospects.filter(p => p.etape === e)
            const pct = prospects.length > 0 ? (pp.length / prospects.length) * 100 : 0
            const cfg = ETAPE_CFG[e]
            return (
              <div key={e} className="flex items-center gap-3">
                <span className="text-xs text-gray-500 w-28 flex-shrink-0">{cfg.label}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-2">
                  <div className={clsx('h-2 rounded-full', cfg.bg.replace('bg-', 'bg-').split(' ')[0])}
                    style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs font-medium text-gray-700 w-8 text-right">{pp.length}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─── Page principale ──────────────────────────────────────────────────────────

type OngletCommercial = 'pipeline' | 'prospects' | 'performances' | 'rapports'

export function CommercialPage() {
  const [onglet, setOnglet] = useState<OngletCommercial>('pipeline')
  const [prospects, setProspects] = useState<Prospect[]>(DEMO_PROSPECTS)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Prospect | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    nom: '', telephone: '', email: '', branche_interet: 'auto', commercial_assigne: COMMERCIAUX[0], valeur_estimee: '', notes: '',
  })

  const filtered = prospects.filter(p =>
    !search || p.nom.toLowerCase().includes(search.toLowerCase()) ||
    p.commercial_assigne.toLowerCase().includes(search.toLowerCase())
  )

  const ajouterProspect = () => {
    const produit = PRODUITS_PROSPECTION.find(p => p.value === form.branche_interet)
    const n: Prospect = {
      id: Date.now().toString(), nom: form.nom, telephone: form.telephone, email: form.email,
      branche_interet: form.branche_interet, famille: (produit?.famille || 'non_vie') as 'vie' | 'non_vie',
      etape: 'lead', valeur_estimee: parseFloat(form.valeur_estimee) || 0,
      date_creation: new Date().toISOString().slice(0, 10),
      commercial_assigne: form.commercial_assigne, notes: form.notes, documents_envoyes: [],
    }
    setProspects(prev => [n, ...prev])
    setShowForm(false)
    setForm({ nom: '', telephone: '', email: '', branche_interet: 'auto', commercial_assigne: COMMERCIAUX[0], valeur_estimee: '', notes: '' })
  }

  const updateProspect = (p: Prospect) => setProspects(prev => prev.map(pp => pp.id === p.id ? p : pp))

  const totalPipeline = prospects.filter(p => !['gagne', 'perdu'].includes(p.etape)).reduce((s, p) => s + p.valeur_estimee, 0)

  return (
    <div className="p-6 space-y-5 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Commercial & Prospection</h1>
          <p className="text-sm text-gray-400">{prospects.length} prospects · Pipeline actif : {(totalPipeline / 1_000_000).toFixed(1)} M FCFA</p>
          <DemoBanner className="mt-2" message="Données de démonstration — connectez votre CRM pour voir vos prospects réels." />
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700">
          <PlusIcon className="h-4 w-4" /> Nouveau prospect
        </button>
      </div>

      {/* Onglets */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {([
          { id: 'pipeline', label: 'Pipeline Kanban', icon: ArrowTrendingUpIcon },
          { id: 'prospects', label: 'Tous les prospects', icon: UserGroupIcon },
          { id: 'performances', label: 'Performances', icon: ChartBarIcon },
          { id: 'rapports', label: 'Rapports', icon: DocumentTextIcon },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id)}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              onglet === id ? 'bg-white text-primary-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            )}>
            <Icon className="h-4 w-4" />{label}
          </button>
        ))}
      </div>

      {/* Formulaire nouveau prospect */}
      {showForm && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-800">Nouveau prospect</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { key: 'nom', label: 'Nom / Entreprise *', type: 'text' },
              { key: 'telephone', label: 'Téléphone', type: 'tel' },
              { key: 'email', label: 'Email', type: 'email' },
              { key: 'valeur_estimee', label: 'Valeur estimée (FCFA)', type: 'number' },
            ].map(f => (
              <div key={f.key}>
                <label className="block text-xs text-gray-500 mb-1">{f.label}</label>
                <input type={f.type} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  value={(form as Record<string, string>)[f.key]}
                  onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} />
              </div>
            ))}
            <div>
              <label className="block text-xs text-gray-500 mb-1">Produit d'intérêt</label>
              <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={form.branche_interet} onChange={e => setForm(p => ({ ...p, branche_interet: e.target.value }))}>
                <optgroup label="Non-Vie">
                  {PRODUITS_PROSPECTION.filter(p => p.famille === 'non_vie').map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </optgroup>
                <optgroup label="Vie & Épargne">
                  {PRODUITS_PROSPECTION.filter(p => p.famille === 'vie').map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </optgroup>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Commercial assigné</label>
              <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={form.commercial_assigne} onChange={e => setForm(p => ({ ...p, commercial_assigne: e.target.value }))}>
                {COMMERCIAUX.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="col-span-full">
              <label className="block text-xs text-gray-500 mb-1">Notes</label>
              <textarea className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm h-16 resize-none"
                value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={ajouterProspect} disabled={!form.nom}
              className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-primary-700 disabled:opacity-50">
              Enregistrer
            </button>
            <button onClick={() => setShowForm(false)} className="border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50">
              Annuler
            </button>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="relative max-w-xs">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Rechercher…"
          className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-xl text-sm focus:border-primary-500 outline-none" />
      </div>

      {/* Kanban */}
      {onglet === 'pipeline' && (
        <div className="flex-1 overflow-x-auto">
          <div className="flex gap-4 pb-4" style={{ minWidth: 'max-content' }}>
            {ETAPES.map(e => (
              <KanbanColumn key={e} etape={e} prospects={filtered.filter(p => p.etape === e)} onSelect={setSelected} />
            ))}
          </div>
        </div>
      )}

      {/* Liste prospects */}
      {onglet === 'prospects' && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden flex-1">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                {['Prospect', 'Produit', 'Famille', 'Étape', 'Valeur', 'Commercial', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(p => {
                const cfg = ETAPE_CFG[p.etape]
                const produit = PRODUITS_PROSPECTION.find(pp => pp.value === p.branche_interet)
                return (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{p.nom}</p>
                      {p.telephone && <p className="text-xs text-gray-500">{p.telephone}</p>}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{produit?.label || p.branche_interet}</td>
                    <td className="px-4 py-3">
                      <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium',
                        p.famille === 'vie' ? 'bg-rose-100 text-rose-700' : 'bg-blue-100 text-blue-700')}>
                        {p.famille === 'vie' ? '❤️ Vie' : '🛡️ Non-Vie'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', cfg.bg, cfg.couleur)}>
                        {cfg.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {new Intl.NumberFormat('fr-FR').format(p.valeur_estimee)} FCFA
                    </td>
                    <td className="px-4 py-3 text-gray-600">{p.commercial_assigne}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => setSelected(p)}
                        className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 font-medium">
                        <DocumentTextIcon className="h-3.5 w-3.5" /> Ouvrir
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Performances */}
      {onglet === 'performances' && <OngletPerformances prospects={prospects} />}

      {/* Rapports */}
      {onglet === 'rapports' && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <RapportsModule module="commercial" />
        </div>
      )}

      {/* Modal détail prospect */}
      {selected && (
        <ProspectDetail p={selected} onClose={() => setSelected(null)} onUpdate={updateProspect} />
      )}
    </div>
  )
}
