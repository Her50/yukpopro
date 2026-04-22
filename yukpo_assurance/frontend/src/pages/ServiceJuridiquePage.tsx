/**
 * ServiceJuridiquePage — Module Service Juridique
 *
 * Fonctionnalités :
 * - Dashboard juridique (dossiers, délais, risques)
 * - Correspondances juridiques via CorrespondancesModule (module="juridique")
 * - Assistant IA juridique CIMA (rédaction de lettres, analyse de contrats, jurisprudence)
 * - Paramétrage des modèles de lettres juridiques
 * - Suivi des litiges et contentieux
 */
import { useState } from 'react'
import {
  ScaleIcon,
  DocumentTextIcon,
  SparklesIcon,
  PencilSquareIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ClockIcon,
  ArrowDownTrayIcon,
  CogIcon,
  PlusIcon,
  TrashIcon,
  PencilIcon,
  XMarkIcon,
  ChevronRightIcon,
  InformationCircleIcon,
  BookOpenIcon,
  UserCircleIcon,
  BriefcaseIcon,
  ShieldExclamationIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'
import { CorrespondancesModule } from '../components/CorrespondancesModule'
import { apiClient } from '../api/client'

// ─── Types ─────────────────────────────────────────────────────────────────────

type OngletJuridique = 'dashboard' | 'correspondances' | 'assistant_ia' | 'modeles' | 'litiges'

type StatutDossier = 'ouvert' | 'en_instruction' | 'audience' | 'clos_favorable' | 'clos_defavorable' | 'transige'

type TypeLitige =
  | 'contentieux_sinistre'
  | 'litige_police'
  | 'recours_tiers'
  | 'contentieux_commercial'
  | 'arbitrage_cima'
  | 'mise_en_demeure'
  | 'litige_intermediaire'

interface DossierLitige {
  id: string
  reference: string
  type: TypeLitige
  titre: string
  partie_adverse: string
  avocat?: string
  montant_litige: number
  statut: StatutDossier
  date_ouverture: string
  prochaine_echeance?: string
  juridiction?: string
  risque: 'faible' | 'moyen' | 'eleve'
  notes?: string
}

interface ModeleLettreJuridique {
  id: string
  label: string
  categorie: string
  description: string
  contenu_defaut: string
  variables: string[]
  actif: boolean
}

// ─── Données démo ───────────────────────────────────────────────────────────────

const DOSSIERS_DEMO: DossierLitige[] = [
  {
    id: '1',
    reference: 'JUR-2026-001',
    type: 'contentieux_sinistre',
    titre: 'Contestation indemnisation sinistre auto — Moulaye Ahmed',
    partie_adverse: 'Moulaye Ahmed & Associés',
    avocat: 'Me Kouassi Jean-Baptiste',
    montant_litige: 8500000,
    statut: 'en_instruction',
    date_ouverture: '2026-01-15',
    prochaine_echeance: '2026-04-25',
    juridiction: 'TGI Douala',
    risque: 'moyen',
  },
  {
    id: '2',
    reference: 'JUR-2026-002',
    type: 'arbitrage_cima',
    titre: 'Arbitrage CIMA — Délai de règlement sinistre incendie',
    partie_adverse: 'CIMA — Commission Régionale de Contrôle',
    montant_litige: 0,
    statut: 'audience',
    date_ouverture: '2026-02-03',
    prochaine_echeance: '2026-04-18',
    juridiction: 'Commission Régionale CIMA',
    risque: 'eleve',
  },
  {
    id: '3',
    reference: 'JUR-2026-003',
    type: 'recours_tiers',
    titre: 'Recours subrogatoire — Sinistre transport SIN-2025-089',
    partie_adverse: 'CAMTRANS SARL',
    avocat: 'Me Ngo Biyong Claire',
    montant_litige: 12000000,
    statut: 'ouvert',
    date_ouverture: '2026-03-10',
    prochaine_echeance: '2026-05-10',
    juridiction: 'TGI Yaoundé',
    risque: 'moyen',
  },
  {
    id: '4',
    reference: 'JUR-2025-018',
    type: 'contentieux_commercial',
    titre: 'Litige commission courtier — Cabinet ASCO',
    partie_adverse: 'Cabinet ASCO',
    avocat: 'Me Kouassi Jean-Baptiste',
    montant_litige: 2300000,
    statut: 'transige',
    date_ouverture: '2025-11-22',
    risque: 'faible',
  },
]

const MODELES_DEMO: ModeleLettreJuridique[] = [
  {
    id: 'mise_en_demeure',
    label: 'Mise en demeure',
    categorie: 'Contentieux',
    description: 'Lettre de mise en demeure formelle avant procédure judiciaire',
    contenu_defaut: 'Douala, le {{date}}\n\nMise en Demeure\n\nMonsieur/Madame {{destinataire}},\n\nPar la présente, nous vous mettons en demeure de {{objet}} dans un délai de {{delai}} jours à compter de la réception de ce courrier.\n\nA défaut, nous nous réservons le droit d\'engager toute procédure judiciaire utile.\n\nSous toutes réserves,\n{{signataire}}',
    variables: ['date', 'destinataire', 'objet', 'delai', 'signataire'],
    actif: true,
  },
  {
    id: 'assignation',
    label: 'Notification assignation',
    categorie: 'Procédure judiciaire',
    description: 'Notification d\'assignation en justice à la partie adverse',
    contenu_defaut: 'Douala, le {{date}}\n\nNotification d\'assignation\n\nMonsieur/Madame {{destinataire}},\n\nNous vous informons que notre compagnie a engagé une procédure judiciaire à votre encontre devant {{juridiction}} relativement à {{objet}}.\n\nVous êtes assigné(e) à comparaître à l\'audience du {{date_audience}}.\n\nCordialement,\n{{signataire}}',
    variables: ['date', 'destinataire', 'juridiction', 'objet', 'date_audience', 'signataire'],
    actif: true,
  },
  {
    id: 'accord_transactionnel',
    label: 'Accord transactionnel',
    categorie: 'Résolution amiable',
    description: 'Protocole d\'accord pour règlement à l\'amiable d\'un litige',
    contenu_defaut: 'Douala, le {{date}}\n\nAccord Transactionnel\n\nEntre les soussignés :\n- {{compagnie}}, représentée par {{representant}}\n- {{partie_adverse}}\n\nIl est convenu ce qui suit :\n\nArticle 1 : La compagnie s\'engage à verser la somme de {{montant}} à titre transactionnel.\nArticle 2 : En contrepartie, {{partie_adverse}} renonce à tout recours judiciaire.\nArticle 3 : Le présent accord a force de chose jugée.\n\nFait à Douala, le {{date_signature}}',
    variables: ['date', 'compagnie', 'representant', 'partie_adverse', 'montant', 'date_signature'],
    actif: true,
  },
  {
    id: 'recours_cima',
    label: 'Recours devant la CIMA',
    categorie: 'Régulation CIMA',
    description: 'Mémoire en défense ou recours devant la Commission Régionale CIMA',
    contenu_defaut: 'Douala, le {{date}}\n\nà l\'attention de la Commission Régionale de Contrôle des Assurances\n\nObjet : {{objet}}\n\nMonsieur le Président de la Commission,\n\nNous avons l\'honneur de porter à votre connaissance les éléments suivants en réponse à la requête N° {{ref_cima}} :\n\n{{argumentation}}\n\nNous sollicitons votre bienveillance pour...\n\nVeuillez agréer, Monsieur le Président, l\'expression de notre haute considération.\n\n{{signataire}}',
    variables: ['date', 'objet', 'ref_cima', 'argumentation', 'signataire'],
    actif: true,
  },
  {
    id: 'convention_subrogation',
    label: 'Convention de subrogation',
    categorie: 'Recours subrogatoire',
    description: 'Convention pour exercice du recours subrogatoire après indemnisation',
    contenu_defaut: 'CONVENTION DE SUBROGATION\n\nEntre {{compagnie}} (ci-après « l\'Assureur ») et {{assure}} (ci-après « l\'Assuré »),\n\nAttendu que l\'Assureur a indemnisé l\'Assuré pour le sinistre {{ref_sinistre}} d\'un montant de {{montant}},\n\nL\'Assuré subroge irrévocablement l\'Assureur dans tous ses droits et actions contre {{responsable}} à concurrence de la somme susmentionnée.\n\nFait à Douala, le {{date}}',
    variables: ['compagnie', 'assure', 'ref_sinistre', 'montant', 'responsable', 'date'],
    actif: true,
  },
  {
    id: 'requete_arbitrage',
    label: 'Requête en arbitrage',
    categorie: 'Arbitrage CIMA',
    description: 'Requête aux fins d\'arbitrage selon le règlement CIMA',
    contenu_defaut: 'Douala, le {{date}}\n\nREQUÊTE EN ARBITRAGE\n\nConformément aux articles 308 et suivants du Code CIMA,\n\n{{compagnie}}, demande la désignation d\'un arbitre pour connaître du litige l\'opposant à {{partie_adverse}} au sujet de {{objet}}.\n\nMontant en litige : {{montant}} XAF\n\nNous joignons à la présente :\n- Contrat d\'assurance N° {{police}}\n- Correspondances échangées\n- Documents justificatifs\n\nNous nous en remettons à la sagesse de la Commission.\n\n{{signataire}}',
    variables: ['date', 'compagnie', 'partie_adverse', 'objet', 'montant', 'police', 'signataire'],
    actif: true,
  },
]

// ─── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (n: number) => n.toLocaleString('fr-FR') + ' XAF'

const STATUT_CFG: Record<StatutDossier, { label: string; bg: string }> = {
  ouvert: { label: 'Ouvert', bg: 'bg-blue-100 text-blue-700' },
  en_instruction: { label: 'En instruction', bg: 'bg-amber-100 text-amber-700' },
  audience: { label: 'Audience', bg: 'bg-purple-100 text-purple-700' },
  clos_favorable: { label: 'Favorable', bg: 'bg-green-100 text-green-700' },
  clos_defavorable: { label: 'Défavorable', bg: 'bg-red-100 text-red-600' },
  transige: { label: 'Transigé', bg: 'bg-teal-100 text-teal-700' },
}

const RISQUE_CFG = {
  faible: { label: 'Risque faible', bg: 'bg-green-50 text-green-700 border border-green-200' },
  moyen: { label: 'Risque moyen', bg: 'bg-amber-50 text-amber-700 border border-amber-200' },
  eleve: { label: 'Risque élevé', bg: 'bg-red-50 text-red-700 border border-red-200' },
}

// ─── Sous-composants ───────────────────────────────────────────────────────────

function OngletDashboard({ dossiers }: { dossiers: DossierLitige[] }) {
  const actifs = dossiers.filter(d => !['clos_favorable', 'clos_defavorable', 'transige'].includes(d.statut))
  const totalLitige = dossiers.reduce((s, d) => s + d.montant_litige, 0)
  const enAudience = dossiers.filter(d => d.statut === 'audience').length
  const risqueEleve = dossiers.filter(d => d.risque === 'eleve').length

  const today = new Date()
  const echeances = dossiers
    .filter(d => d.prochaine_echeance)
    .map(d => ({ ...d, diff: Math.ceil((new Date(d.prochaine_echeance!).getTime() - today.getTime()) / 86400000) }))
    .sort((a, b) => a.diff - b.diff)
    .slice(0, 4)

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Dossiers actifs', value: actifs.length.toString(), icon: BriefcaseIcon, color: 'text-blue-600 bg-blue-50' },
          { label: 'Montant en litige', value: fmt(totalLitige), icon: ScaleIcon, color: 'text-amber-600 bg-amber-50' },
          { label: 'Audiences en cours', value: enAudience.toString(), icon: ShieldExclamationIcon, color: 'text-purple-600 bg-purple-50' },
          { label: 'Risque élevé', value: risqueEleve.toString(), icon: ExclamationTriangleIcon, color: 'text-red-600 bg-red-50' },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="flex items-center gap-3 mb-2">
              <div className={`${k.color} p-2 rounded-lg flex-shrink-0`}>
                <k.icon className="w-5 h-5" />
              </div>
              <p className="text-xs text-gray-500">{k.label}</p>
            </div>
            <p className="text-base font-bold text-gray-900">{k.value}</p>
          </div>
        ))}
      </div>

      {/* Conformité CIMA */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
        <InformationCircleIcon className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-amber-800">Délais réglementaires CIMA</p>
          <p className="text-xs text-amber-700 mt-0.5">
            Art. 12 Code CIMA : délai de règlement sinistre <strong>30 jours</strong> après production pièces.
            Art. 18 : tout rejet doit être motivé par écrit. Art. 308 : recours arbitrage CIMA possible avant juridiction.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Prochaines échéances */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <ClockIcon className="h-4 w-4 text-primary-600" />
            Prochaines échéances
          </h3>
          <div className="space-y-3">
            {echeances.length === 0 && <p className="text-xs text-gray-400">Aucune échéance à venir</p>}
            {echeances.map(d => (
              <div key={d.id} className="flex items-center gap-3">
                <div className={clsx('w-10 h-10 rounded-lg flex flex-col items-center justify-center text-center flex-shrink-0',
                  d.diff < 7 ? 'bg-red-100 text-red-700' : d.diff < 30 ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'
                )}>
                  <span className="text-sm font-bold leading-none">{d.diff < 0 ? '!' : d.diff}</span>
                  <span className="text-[9px]">{d.diff < 0 ? 'Passée' : 'j'}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-gray-800 truncate">{d.titre}</p>
                  <p className="text-xs text-gray-500">{d.reference} · {d.juridiction || 'Interne'}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${STATUT_CFG[d.statut].bg}`}>
                  {STATUT_CFG[d.statut].label}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Répartition par type */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <ScaleIcon className="h-4 w-4 text-primary-600" />
            Dossiers par statut
          </h3>
          <div className="space-y-2">
            {(Object.entries(STATUT_CFG) as [StatutDossier, typeof STATUT_CFG[StatutDossier]][]).map(([key, cfg]) => {
              const count = dossiers.filter(d => d.statut === key).length
              if (!count) return null
              const pct = Math.round((count / dossiers.length) * 100)
              return (
                <div key={key} className="space-y-1">
                  <div className="flex justify-between text-xs text-gray-600">
                    <span>{cfg.label}</span>
                    <span className="font-medium">{count}</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-primary-500 rounded-full" style={{ width: `${pct}%` }} />
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

// ─── Onglet Litiges ─────────────────────────────────────────────────────────────

function OngletLitiges({ dossiers, setDossiers }: { dossiers: DossierLitige[]; setDossiers: React.Dispatch<React.SetStateAction<DossierLitige[]>> }) {
  const [filtre, setFiltre] = useState<StatutDossier | 'tous'>('tous')
  const [selected, setSelected] = useState<DossierLitige | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<Partial<DossierLitige>>({})

  const filtered = filtre === 'tous' ? dossiers : dossiers.filter(d => d.statut === filtre)

  const sauvegarder = () => {
    if (!form.titre || !form.partie_adverse) return
    if (form.id) {
      setDossiers(prev => prev.map(d => d.id === form.id ? { ...d, ...form } as DossierLitige : d))
    } else {
      const nouveau: DossierLitige = {
        id: Date.now().toString(),
        reference: `JUR-2026-${String(dossiers.length + 1).padStart(3, '0')}`,
        type: (form.type as TypeLitige) || 'contentieux_sinistre',
        titre: form.titre || '',
        partie_adverse: form.partie_adverse || '',
        avocat: form.avocat,
        montant_litige: Number(form.montant_litige) || 0,
        statut: (form.statut as StatutDossier) || 'ouvert',
        date_ouverture: form.date_ouverture || new Date().toISOString().slice(0, 10),
        prochaine_echeance: form.prochaine_echeance,
        juridiction: form.juridiction,
        risque: (form.risque as 'faible' | 'moyen' | 'eleve') || 'moyen',
        notes: form.notes,
      }
      setDossiers(prev => [nouveau, ...prev])
    }
    setShowForm(false)
    setForm({})
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-2 flex-wrap">
          {(['tous', 'ouvert', 'en_instruction', 'audience', 'transige', 'clos_favorable', 'clos_defavorable'] as const).map(s => (
            <button key={s} onClick={() => setFiltre(s)}
              className={clsx('px-3 py-1 rounded-full text-xs font-medium border transition-colors',
                filtre === s ? 'bg-primary-600 text-white border-primary-600' : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
              )}>
              {s === 'tous' ? 'Tous' : STATUT_CFG[s].label}
            </button>
          ))}
        </div>
        <button onClick={() => { setForm({}); setShowForm(true) }}
          className="flex items-center gap-1 bg-primary-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-primary-700">
          <PlusIcon className="h-4 w-4" />
          Nouveau dossier
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {['Référence', 'Dossier', 'Partie adverse', 'Montant', 'Risque', 'Statut', 'Échéance', ''].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-600">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map(d => (
              <tr key={d.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 text-xs font-mono text-gray-500">{d.reference}</td>
                <td className="px-4 py-3 max-w-xs">
                  <p className="font-medium text-gray-800 truncate">{d.titre}</p>
                  <p className="text-xs text-gray-400">{d.juridiction || '—'}</p>
                </td>
                <td className="px-4 py-3 text-xs text-gray-600">{d.partie_adverse}</td>
                <td className="px-4 py-3 text-xs font-medium text-gray-700">
                  {d.montant_litige > 0 ? fmt(d.montant_litige) : '—'}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${RISQUE_CFG[d.risque].bg}`}>
                    {RISQUE_CFG[d.risque].label}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUT_CFG[d.statut].bg}`}>
                    {STATUT_CFG[d.statut].label}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {d.prochaine_echeance ? new Date(d.prochaine_echeance).toLocaleDateString('fr-FR') : '—'}
                </td>
                <td className="px-4 py-3">
                  <button onClick={() => setSelected(d)}
                    className="text-primary-600 hover:text-primary-700 text-xs font-medium flex items-center gap-1">
                    Voir <ChevronRightIcon className="h-3 w-3" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="py-10 text-center text-sm text-gray-400">Aucun dossier pour ce filtre</div>
        )}
      </div>

      {/* Détail dossier */}
      {selected && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-mono text-gray-400">{selected.reference}</p>
                <h3 className="text-base font-bold text-gray-900 mt-0.5">{selected.titre}</h3>
              </div>
              <button onClick={() => setSelected(null)}>
                <XMarkIcon className="h-5 w-5 text-gray-400 hover:text-gray-600" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><p className="text-xs text-gray-500">Partie adverse</p><p className="font-medium text-gray-800">{selected.partie_adverse}</p></div>
              <div><p className="text-xs text-gray-500">Avocat</p><p className="font-medium text-gray-800">{selected.avocat || '—'}</p></div>
              <div><p className="text-xs text-gray-500">Montant</p><p className="font-medium text-gray-800">{selected.montant_litige > 0 ? fmt(selected.montant_litige) : '—'}</p></div>
              <div><p className="text-xs text-gray-500">Juridiction</p><p className="font-medium text-gray-800">{selected.juridiction || '—'}</p></div>
              <div><p className="text-xs text-gray-500">Ouverture</p><p className="font-medium text-gray-800">{new Date(selected.date_ouverture).toLocaleDateString('fr-FR')}</p></div>
              <div><p className="text-xs text-gray-500">Prochaine échéance</p><p className="font-medium text-gray-800">{selected.prochaine_echeance ? new Date(selected.prochaine_echeance).toLocaleDateString('fr-FR') : '—'}</p></div>
            </div>
            {selected.notes && <p className="text-xs text-gray-600 bg-gray-50 rounded-lg p-3">{selected.notes}</p>}
            <div className="flex gap-2 pt-2">
              <button onClick={() => { setForm(selected); setSelected(null); setShowForm(true) }}
                className="flex-1 flex items-center justify-center gap-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50">
                <PencilIcon className="h-4 w-4" /> Modifier
              </button>
              <button onClick={() => {
                setDossiers(prev => prev.filter(d => d.id !== selected.id))
                setSelected(null)
              }}
                className="flex items-center gap-1 border border-red-300 text-red-600 rounded-lg px-4 py-2 text-sm hover:bg-red-50">
                <TrashIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Formulaire */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-900">{form.id ? 'Modifier le dossier' : 'Nouveau dossier juridique'}</h3>
              <button onClick={() => setShowForm(false)}><XMarkIcon className="h-5 w-5 text-gray-400" /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 mb-1">Titre du dossier *</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.titre || ''} onChange={e => setForm(f => ({ ...f, titre: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Type</label>
                <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.type || ''} onChange={e => setForm(f => ({ ...f, type: e.target.value as TypeLitige }))}>
                  <option value="contentieux_sinistre">Contentieux sinistre</option>
                  <option value="litige_police">Litige police</option>
                  <option value="recours_tiers">Recours tiers</option>
                  <option value="contentieux_commercial">Contentieux commercial</option>
                  <option value="arbitrage_cima">Arbitrage CIMA</option>
                  <option value="mise_en_demeure">Mise en demeure</option>
                  <option value="litige_intermediaire">Litige intermédiaire</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Statut</label>
                <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.statut || 'ouvert'} onChange={e => setForm(f => ({ ...f, statut: e.target.value as StatutDossier }))}>
                  {Object.entries(STATUT_CFG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 mb-1">Partie adverse *</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.partie_adverse || ''} onChange={e => setForm(f => ({ ...f, partie_adverse: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Avocat</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="Me Nom Prénom" value={form.avocat || ''} onChange={e => setForm(f => ({ ...f, avocat: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Montant litige (XAF)</label>
                <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.montant_litige || ''} onChange={e => setForm(f => ({ ...f, montant_litige: Number(e.target.value) }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Juridiction</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="TGI Douala..." value={form.juridiction || ''} onChange={e => setForm(f => ({ ...f, juridiction: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Prochaine échéance</label>
                <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.prochaine_echeance || ''} onChange={e => setForm(f => ({ ...f, prochaine_echeance: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Niveau de risque</label>
                <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={form.risque || 'moyen'} onChange={e => setForm(f => ({ ...f, risque: e.target.value as 'faible' | 'moyen' | 'eleve' }))}>
                  <option value="faible">Faible</option>
                  <option value="moyen">Moyen</option>
                  <option value="eleve">Élevé</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 mb-1">Notes</label>
                <textarea className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm h-20 resize-none" value={form.notes || ''} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
            <button onClick={sauvegarder}
              disabled={!form.titre || !form.partie_adverse}
              className="w-full bg-primary-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-primary-700 disabled:opacity-50">
              {form.id ? 'Enregistrer' : 'Créer le dossier'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Onglet Assistant IA ─────────────────────────────────────────────────────────

interface MessageIA {
  role: 'user' | 'assistant'
  content: string
}

function OngletAssistantIA({ dossiers }: { dossiers: DossierLitige[] }) {
  const [messages, setMessages] = useState<MessageIA[]>([
    {
      role: 'assistant',
      content: 'Bonjour ! Je suis Yukpo Juridique, votre assistant IA spécialisé en droit des assurances (Code CIMA, droit OHADA, droit camerounais). Posez-moi vos questions : rédaction de lettres juridiques, analyse de clauses de police, jurisprudence CIMA, délais de prescription, recours, etc.',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [contexteChoisi, setContexteChoisi] = useState('')

  const questions_suggerees = [
    'Quels sont les délais de prescription en assurance CIMA ?',
    'Comment rédiger une mise en demeure conforme au Code CIMA ?',
    'Quelles sont les conditions d\'un recours subrogatoire ?',
    'Procédure d\'arbitrage CIMA — Art. 308 et suivants',
    'Clauses abusives dans un contrat d\'assurance CIMA',
    'Délai de règlement sinistre obligatoire — Art. 12 CIMA',
  ]

  const envoyer = async (msg?: string) => {
    const texte = msg || input.trim()
    if (!texte) return
    const nouveauUser: MessageIA = { role: 'user', content: texte }
    setMessages(prev => [...prev, nouveauUser])
    setInput('')
    setLoading(true)
    try {
      const contexte = contexteChoisi
        ? `Contexte dossier : ${dossiers.find(d => d.id === contexteChoisi)?.titre || ''} — ${dossiers.find(d => d.id === contexteChoisi)?.reference || ''}.`
        : ''
      const { data } = await apiClient.post('/api/v1/chat/message', {
        message: `${contexte} Question juridique assurance CIMA/Cameroun : ${texte}. Réponds en juriste spécialiste du droit des assurances africain, cite les articles du Code CIMA pertinents, la jurisprudence applicable et les bonnes pratiques.`,
        stream: false,
      })
      const d = data as Record<string, unknown>
      setMessages(prev => [...prev, { role: 'assistant', content: (d.response as string) || (d.content as string) || 'Réponse non disponible.' }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Réponse IA non disponible (mode démo).\n\nSur la question : "${texte}"\n\n**Éléments de réponse (Code CIMA) :**\n\n• Art. 12 : Délai de règlement sinistre 30 jours après production pièces complètes\n• Art. 18 : Tout rejet doit être notifié avec motifs par écrit\n• Art. 308 : Recours arbitrage CIMA avant juridiction ordinaire\n• Art. 13 : Prescription biennale pour les actions dérivant du contrat d'assurance\n\nPour une analyse approfondie, connectez le backend Yukpo IA.`,
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Contexte dossier */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <label className="block text-xs font-medium text-gray-600 mb-2">
          <BookOpenIcon className="h-3.5 w-3.5 inline mr-1" />
          Contextualiser avec un dossier (optionnel)
        </label>
        <select
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          value={contexteChoisi}
          onChange={e => setContexteChoisi(e.target.value)}
        >
          <option value="">— Sans contexte spécifique —</option>
          {dossiers.map(d => (
            <option key={d.id} value={d.id}>{d.reference} — {d.titre}</option>
          ))}
        </select>
      </div>

      {/* Chat */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col" style={{ height: '480px' }}>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((m, i) => (
            <div key={i} className={clsx('flex gap-3', m.role === 'user' ? 'justify-end' : 'justify-start')}>
              {m.role === 'assistant' && (
                <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                  <ScaleIcon className="h-4 w-4 text-primary-600" />
                </div>
              )}
              <div className={clsx('max-w-2xl rounded-2xl px-4 py-3 text-sm',
                m.role === 'user'
                  ? 'bg-primary-600 text-white rounded-tr-sm'
                  : 'bg-gray-50 text-gray-800 border border-gray-200 rounded-tl-sm'
              )}>
                <p className="whitespace-pre-wrap">{m.content}</p>
              </div>
              {m.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                  <UserCircleIcon className="h-5 w-5 text-gray-500" />
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                <ScaleIcon className="h-4 w-4 text-primary-600" />
              </div>
              <div className="bg-gray-50 border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Questions suggérées */}
        <div className="border-t border-gray-100 px-4 py-2">
          <div className="flex gap-2 overflow-x-auto pb-1">
            {questions_suggerees.map(q => (
              <button key={q} onClick={() => envoyer(q)}
                className="flex-shrink-0 text-xs px-3 py-1.5 bg-primary-50 text-primary-700 border border-primary-200 rounded-full hover:bg-primary-100 transition-colors">
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 p-3 flex gap-2">
          <input
            className="flex-1 border border-gray-300 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:outline-none"
            placeholder="Posez votre question juridique CIMA…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); envoyer() } }}
            disabled={loading}
          />
          <button
            onClick={() => envoyer()}
            disabled={!input.trim() || loading}
            className="bg-primary-600 text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1.5"
          >
            <SparklesIcon className="h-4 w-4" />
            Envoyer
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Onglet Modèles ──────────────────────────────────────────────────────────────

function OngletModeles() {
  const [modeles, setModeles] = useState<ModeleLettreJuridique[]>(MODELES_DEMO)
  const [selected, setSelected] = useState<ModeleLettreJuridique | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [draft, setDraft] = useState<ModeleLettreJuridique | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [newForm, setNewForm] = useState<Partial<ModeleLettreJuridique>>({})

  const sauvegarderModele = () => {
    if (!draft) return
    setModeles(prev => prev.map(m => m.id === draft.id ? draft : m))
    setSelected(draft)
    setEditMode(false)
  }

  const creerModele = () => {
    if (!newForm.label || !newForm.contenu_defaut) return
    const m: ModeleLettreJuridique = {
      id: `custom_${Date.now()}`,
      label: newForm.label || '',
      categorie: newForm.categorie || 'Personnalisé',
      description: newForm.description || '',
      contenu_defaut: newForm.contenu_defaut || '',
      variables: (newForm.contenu_defaut || '').match(/\{\{(\w+)\}\}/g)?.map(v => v.replace(/\{\{|\}\}/g, '')) || [],
      actif: true,
    }
    setModeles(prev => [...prev, m])
    setShowNew(false)
    setNewForm({})
  }

  const categories = [...new Set(modeles.map(m => m.categorie))]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Liste modèles */}
      <div className="lg:col-span-1 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-800">Modèles configurés</h3>
          <button onClick={() => setShowNew(true)}
            className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 font-medium">
            <PlusIcon className="h-3.5 w-3.5" /> Ajouter
          </button>
        </div>
        {categories.map(cat => (
          <div key={cat}>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">{cat}</p>
            <div className="space-y-1.5">
              {modeles.filter(m => m.categorie === cat).map(m => (
                <button key={m.id}
                  onClick={() => { setSelected(m); setDraft(m); setEditMode(false) }}
                  className={clsx('w-full text-left p-3 rounded-xl border transition-all',
                    selected?.id === m.id ? 'border-primary-400 bg-primary-50' : 'border-gray-200 hover:border-gray-300 bg-white'
                  )}>
                  <div className="flex items-center justify-between mb-0.5">
                    <p className="text-xs font-semibold text-gray-800">{m.label}</p>
                    <span className={clsx('w-1.5 h-1.5 rounded-full', m.actif ? 'bg-green-500' : 'bg-gray-300')} />
                  </div>
                  <p className="text-xs text-gray-500 line-clamp-1">{m.description}</p>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Éditeur modèle */}
      <div className="lg:col-span-2">
        {selected ? (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-gray-900">{selected.label}</h3>
                <p className="text-xs text-gray-400 mt-0.5">{selected.categorie} · Variables : {selected.variables.join(', ')}</p>
              </div>
              <div className="flex gap-2">
                {!editMode ? (
                  <button onClick={() => { setDraft({ ...selected }); setEditMode(true) }}
                    className="flex items-center gap-1 text-sm border border-gray-300 text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-50">
                    <PencilIcon className="h-3.5 w-3.5" /> Modifier
                  </button>
                ) : (
                  <>
                    <button onClick={sauvegarderModele}
                      className="flex items-center gap-1 text-sm bg-primary-600 text-white px-3 py-1.5 rounded-lg hover:bg-primary-700">
                      <CheckCircleIcon className="h-3.5 w-3.5" /> Sauvegarder
                    </button>
                    <button onClick={() => { setEditMode(false); setDraft(selected) }}
                      className="text-sm border border-gray-300 text-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50">
                      Annuler
                    </button>
                  </>
                )}
              </div>
            </div>
            {editMode && draft ? (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Nom du modèle</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={draft.label} onChange={e => setDraft({ ...draft, label: e.target.value })} />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Description</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    Contenu — utilisez <code className="bg-gray-100 px-1 rounded">{`{{variable}}`}</code> pour les champs dynamiques
                  </label>
                  <textarea
                    className="w-full border border-gray-300 rounded-xl p-3 text-sm font-mono h-64 resize-none focus:ring-2 focus:ring-primary-500"
                    value={draft.contenu_defaut}
                    onChange={e => setDraft({ ...draft, contenu_defaut: e.target.value, variables: (e.target.value.match(/\{\{(\w+)\}\}/g) || []).map(v => v.replace(/\{\{|\}\}/g, '')) })}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="actif" checked={draft.actif} onChange={e => setDraft({ ...draft, actif: e.target.checked })} className="rounded" />
                  <label htmlFor="actif" className="text-xs text-gray-600">Modèle actif (disponible dans CorrespondancesModule)</label>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-xs text-gray-500 mb-2">Aperçu du contenu</p>
                <pre className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-xs font-mono whitespace-pre-wrap text-gray-700 max-h-72 overflow-y-auto">
                  {selected.contenu_defaut}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
            <DocumentTextIcon className="h-10 w-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-400">Sélectionnez un modèle pour l'éditer</p>
          </div>
        )}
      </div>

      {/* Modal nouveau modèle */}
      {showNew && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowNew(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-900">Nouveau modèle juridique</h3>
              <button onClick={() => setShowNew(false)}><XMarkIcon className="h-5 w-5 text-gray-400" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Nom du modèle *</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={newForm.label || ''} onChange={e => setNewForm(f => ({ ...f, label: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Catégorie</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="ex: Contentieux, Arbitrage…" value={newForm.categorie || ''} onChange={e => setNewForm(f => ({ ...f, categorie: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Description</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={newForm.description || ''} onChange={e => setNewForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  Contenu * — <code className="bg-gray-100 px-1 rounded text-xs">{`{{variable}}`}</code> pour champs dynamiques
                </label>
                <textarea
                  className="w-full border border-gray-300 rounded-xl p-3 text-sm font-mono h-48 resize-none focus:ring-2 focus:ring-primary-500"
                  value={newForm.contenu_defaut || ''}
                  onChange={e => setNewForm(f => ({ ...f, contenu_defaut: e.target.value }))}
                  placeholder={`Douala, le {{date}}\n\nObjet : {{objet}}\n\n...`}
                />
              </div>
            </div>
            <button onClick={creerModele}
              disabled={!newForm.label || !newForm.contenu_defaut}
              className="w-full bg-primary-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-primary-700 disabled:opacity-50">
              Créer le modèle
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Page principale ────────────────────────────────────────────────────────────

export default function ServiceJuridiquePage() {
  const [onglet, setOnglet] = useState<OngletJuridique>('dashboard')
  const [dossiers, setDossiers] = useState<DossierLitige[]>(DOSSIERS_DEMO)

  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ScaleIcon className="h-7 w-7 text-primary-600" />
            Service Juridique
          </h1>
          <p className="text-sm text-gray-500 mt-1">Litiges · Correspondances légales · Assistant IA CIMA · Modèles</p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 text-sm border border-gray-300 bg-white text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50">
            <ArrowDownTrayIcon className="w-4 h-4" />
            Exporter rapport
          </button>
          <button
            onClick={() => setOnglet('assistant_ia')}
            className="flex items-center gap-2 text-sm bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
            <SparklesIcon className="w-4 h-4" />
            Assistant IA
          </button>
        </div>
      </div>

      {/* Onglets */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6 overflow-x-auto">
          {([
            { key: 'dashboard', label: 'Tableau de bord', icon: BriefcaseIcon },
            { key: 'litiges', label: 'Litiges & Contentieux', icon: ScaleIcon },
            { key: 'correspondances', label: 'Correspondances', icon: PencilSquareIcon },
            { key: 'assistant_ia', label: 'Assistant IA Juridique', icon: SparklesIcon },
            { key: 'modeles', label: 'Modèles de lettres', icon: CogIcon },
          ] as const).map(t => (
            <button key={t.key} onClick={() => setOnglet(t.key)}
              className={clsx('flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-colors flex-shrink-0',
                onglet === t.key
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}>
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Contenu */}
      {onglet === 'dashboard' && <OngletDashboard dossiers={dossiers} />}

      {onglet === 'litiges' && (
        <OngletLitiges dossiers={dossiers} setDossiers={setDossiers} />
      )}

      {onglet === 'correspondances' && (
        <CorrespondancesModule
          module="juridique"
          titre="Correspondances — Service Juridique"
          references={dossiers.map(d => ({ value: d.reference, label: `${d.reference} — ${d.titre}` }))}
        />
      )}

      {onglet === 'assistant_ia' && <OngletAssistantIA dossiers={dossiers} />}

      {onglet === 'modeles' && <OngletModeles />}

    </div>
  )
}
