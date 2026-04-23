import { useState } from 'react'
import {
  BanknotesIcon, FunnelIcon, ArrowDownTrayIcon,
  CheckCircleIcon, ExclamationTriangleIcon, ClockIcon,
} from '@heroicons/react/24/outline'
import { clsx } from 'clsx'

// ─── Types ────────────────────────────────────────────────────────────────────

type TypeIntermediaire = 'courtier' | 'agent' | 'apporteur'
type StatutCommission = 'due' | 'payee' | 'en_litige'

interface Commission {
  id: string
  intermediaire: string
  type: TypeIntermediaire
  periode: string
  branche: string
  primes: number
  taux: number
  montant: number
  statut: StatutCommission
  date_paiement?: string
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const DEMO_COMMISSIONS: Commission[] = [
  { id: '1', intermediaire: 'Cabinet Assur-Plus Douala', type: 'courtier', periode: 'Mars 2026', branche: 'Auto', primes: 14_200_000, taux: 12, montant: 1_704_000, statut: 'due' },
  { id: '2', intermediaire: 'Intermédiaire SARL Transcam', type: 'courtier', periode: 'Mars 2026', branche: 'MRH', primes: 8_500_000, taux: 10, montant: 850_000, statut: 'payee', date_paiement: '2026-04-05' },
  { id: '3', intermediaire: 'Agence YK Courtage Yaoundé', type: 'courtier', periode: 'Fév 2026', branche: 'Vie', primes: 22_000_000, taux: 8, montant: 1_760_000, statut: 'en_litige' },
  { id: '4', intermediaire: 'Agent Général Mballa', type: 'agent', periode: 'Mars 2026', branche: 'Auto', primes: 6_400_000, taux: 10, montant: 640_000, statut: 'due' },
  { id: '5', intermediaire: 'Agent Général Mballa', type: 'agent', periode: 'Fév 2026', branche: 'MRH', primes: 3_200_000, taux: 10, montant: 320_000, statut: 'payee', date_paiement: '2026-03-15' },
  { id: '6', intermediaire: 'Apporteur Kouassi J.', type: 'apporteur', periode: 'Mars 2026', branche: 'Santé', primes: 4_800_000, taux: 6, montant: 288_000, statut: 'due' },
  { id: '7', intermediaire: 'Apporteur Fouda P.', type: 'apporteur', periode: 'Mars 2026', branche: 'RC', primes: 2_100_000, taux: 8, montant: 168_000, statut: 'payee', date_paiement: '2026-04-03' },
  { id: '8', intermediaire: 'Cabinet Assur-Plus Douala', type: 'courtier', periode: 'Mars 2026', branche: 'Santé', primes: 5_900_000, taux: 10, montant: 590_000, statut: 'due' },
  { id: '9', intermediaire: 'Courtier Indépendant Ngando', type: 'courtier', periode: 'Mars 2026', branche: 'RC', primes: 3_200_000, taux: 15, montant: 480_000, statut: 'due' },
  { id: '10', intermediaire: 'Agent Général Kouam S.', type: 'agent', periode: 'Fév 2026', branche: 'Vie', primes: 18_500_000, taux: 7, montant: 1_295_000, statut: 'payee', date_paiement: '2026-03-20' },
]

// ─── Utilitaires ──────────────────────────────────────────────────────────────

function fmt(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)} K`
  return `${v}`
}

const TYPE_CFG: Record<TypeIntermediaire, { label: string; icon: string; classes: string }> = {
  courtier: { label: 'Courtier', icon: '🏢', classes: 'bg-blue-100 text-blue-700' },
  agent: { label: 'Agent Général', icon: '👤', classes: 'bg-purple-100 text-purple-700' },
  apporteur: { label: 'Apporteur', icon: '🤝', classes: 'bg-cyan-100 text-cyan-700' },
}

const STATUT_CFG: Record<StatutCommission, { label: string; icon: React.ReactNode; classes: string }> = {
  due: { label: 'Due', icon: <ClockIcon className="h-3.5 w-3.5" />, classes: 'bg-amber-100 text-amber-700' },
  payee: { label: 'Payée', icon: <CheckCircleIcon className="h-3.5 w-3.5" />, classes: 'bg-green-100 text-green-700' },
  en_litige: { label: 'En litige', icon: <ExclamationTriangleIcon className="h-3.5 w-3.5" />, classes: 'bg-red-100 text-red-700' },
}

// ─── Page Commissions ─────────────────────────────────────────────────────────

export function CommissionsPage() {
  const [commissions, setCommissions] = useState<Commission[]>(DEMO_COMMISSIONS)
  const [filtreType, setFiltreType] = useState<TypeIntermediaire | 'tous'>('tous')
  const [filtreStatut, setFiltreStatut] = useState<StatutCommission | 'tous'>('tous')
  const [filtrePeriode, setFiltrePeriode] = useState<string>('tous')

  const periodes = Array.from(new Set(commissions.map(c => c.periode))).sort().reverse()

  let liste = commissions
  if (filtreType !== 'tous') liste = liste.filter(c => c.type === filtreType)
  if (filtreStatut !== 'tous') liste = liste.filter(c => c.statut === filtreStatut)
  if (filtrePeriode !== 'tous') liste = liste.filter(c => c.periode === filtrePeriode)

  const totalDue = commissions.filter(c => c.statut === 'due').reduce((s, c) => s + c.montant, 0)
  const totalPayee = commissions.filter(c => c.statut === 'payee').reduce((s, c) => s + c.montant, 0)
  const totalLitige = commissions.filter(c => c.statut === 'en_litige').reduce((s, c) => s + c.montant, 0)
  const totalFiltre = liste.reduce((s, c) => s + c.montant, 0)

  const payer = (id: string) =>
    setCommissions(prev => prev.map(c => c.id === id
      ? { ...c, statut: 'payee' as const, date_paiement: new Date().toISOString().slice(0, 10) }
      : c))

  const approuver = (id: string) =>
    setCommissions(prev => prev.map(c => c.id === id ? { ...c, statut: 'due' as const } : c))

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Module Commissions</h1>
          <p className="text-sm text-gray-400">Tous intermédiaires — Courtiers · Agents Généraux · Apporteurs</p>
        </div>
        <button className="flex items-center gap-2 text-sm border border-gray-300 px-4 py-2 rounded-lg text-gray-700 hover:bg-gray-50">
          <ArrowDownTrayIcon className="h-4 w-4" /> Exporter
        </button>
      </div>

      {/* KPI résumé */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <ClockIcon className="h-4 w-4 text-amber-600" />
            <p className="text-xs font-medium text-amber-600">Commissions dues</p>
          </div>
          <p className="text-2xl font-bold text-amber-800">{fmt(totalDue)} FCFA</p>
          <p className="text-xs text-amber-600 mt-1">{commissions.filter(c => c.statut === 'due').length} lignes à payer</p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircleIcon className="h-4 w-4 text-green-600" />
            <p className="text-xs font-medium text-green-600">Commissions payées</p>
          </div>
          <p className="text-2xl font-bold text-green-800">{fmt(totalPayee)} FCFA</p>
          <p className="text-xs text-green-600 mt-1">{commissions.filter(c => c.statut === 'payee').length} lignes réglées</p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <ExclamationTriangleIcon className="h-4 w-4 text-red-600" />
            <p className="text-xs font-medium text-red-600">En litige</p>
          </div>
          <p className="text-2xl font-bold text-red-800">{fmt(totalLitige)} FCFA</p>
          <p className="text-xs text-red-600 mt-1">{commissions.filter(c => c.statut === 'en_litige').length} litige(s) en cours</p>
        </div>
      </div>

      {/* Filtres */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <FunnelIcon className="h-4 w-4 text-gray-500 flex-shrink-0" />

          <div className="flex gap-1">
            {(['tous', 'courtier', 'agent', 'apporteur'] as const).map(t => (
              <button key={t} onClick={() => setFiltreType(t)}
                className={clsx('text-xs px-3 py-1 rounded-full border transition-colors',
                  filtreType === t ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50')}>
                {t === 'tous' ? 'Tous types' : TYPE_CFG[t].label}
              </button>
            ))}
          </div>

          <div className="w-px h-5 bg-gray-200" />

          <div className="flex gap-1">
            {(['tous', 'due', 'payee', 'en_litige'] as const).map(s => (
              <button key={s} onClick={() => setFiltreStatut(s)}
                className={clsx('text-xs px-3 py-1 rounded-full border transition-colors',
                  filtreStatut === s ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50')}>
                {s === 'tous' ? 'Tous statuts' : STATUT_CFG[s].label}
              </button>
            ))}
          </div>

          <div className="w-px h-5 bg-gray-200" />

          <select value={filtrePeriode} onChange={e => setFiltrePeriode(e.target.value)}
            className="text-xs border border-gray-300 rounded-lg px-3 py-1 text-gray-700">
            <option value="tous">Toutes périodes</option>
            {periodes.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BanknotesIcon className="h-5 w-5 text-primary-600" />
            <span className="font-semibold text-gray-900 text-sm">{liste.length} ligne(s)</span>
          </div>
          <span className="text-sm text-gray-500">
            Total : <span className="font-bold text-gray-900">{fmt(totalFiltre)} FCFA</span>
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600">Intermédiaire</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600">Type</th>
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
                const tcfg = TYPE_CFG[c.type]
                const scfg = STATUT_CFG[c.statut]
                return (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className="font-medium text-gray-900 text-xs">{c.intermediaire}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', tcfg.classes)}>
                        {tcfg.icon} {tcfg.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{c.periode}</td>
                    <td className="px-4 py-3 text-gray-700 text-xs">{c.branche}</td>
                    <td className="px-4 py-3 text-right text-gray-700 text-xs font-mono">{fmt(c.primes)}</td>
                    <td className="px-4 py-3 text-right text-gray-700 text-xs">{c.taux}%</td>
                    <td className="px-4 py-3 text-right font-bold text-gray-900 text-xs font-mono">{fmt(c.montant)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx('flex items-center justify-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium w-fit mx-auto', scfg.classes)}>
                        {scfg.icon}{scfg.label}
                      </span>
                      {c.date_paiement && (
                        <p className="text-xs text-gray-400 mt-0.5">{c.date_paiement}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex gap-1 justify-end">
                        {c.statut === 'due' && (
                          <button onClick={() => payer(c.id)}
                            className="text-xs bg-green-600 text-white px-2.5 py-1 rounded-lg hover:bg-green-700 whitespace-nowrap">
                            Payer
                          </button>
                        )}
                        {c.statut === 'en_litige' && (
                          <button onClick={() => approuver(c.id)}
                            className="text-xs border border-blue-300 text-blue-600 px-2.5 py-1 rounded-lg hover:bg-blue-50 whitespace-nowrap">
                            Approuver
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {liste.length === 0 && (
          <div className="text-center py-10 text-gray-400 text-sm">
            <BanknotesIcon className="h-8 w-8 mx-auto mb-2" />
            Aucune commission pour ces filtres
          </div>
        )}
      </div>
    </div>
  )
}
