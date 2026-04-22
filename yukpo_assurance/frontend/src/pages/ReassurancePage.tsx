import { useState, useCallback } from 'react'
import {
  ShieldCheckIcon,
  ArrowTrendingUpIcon,
  DocumentChartBarIcon,
  ExclamationTriangleIcon,
  ArrowDownTrayIcon,
  ChartBarIcon,
  InformationCircleIcon,
  DocumentArrowUpIcon,
  FolderOpenIcon,
  CheckCircleIcon,
  ClockIcon,
  EnvelopeIcon,
  BuildingLibraryIcon,
  UserGroupIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline'
import { useDropzone } from 'react-dropzone'
import { ArchiveNumerique } from '../components/ArchiveNumerique'
import { RapportsModule } from '../components/RapportsModule'
import { OngletCourtiers } from './CourtiersPage'
import { CorrespondancesModule } from '../components/CorrespondancesModule'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, Legend, ResponsiveContainer,
} from 'recharts'

// ─── Types ─────────────────────────────────────────────────────────────────

interface TraiteReassurance {
  type: string
  reassureur: string
  quote_part?: number
  plein_de_conservation?: number
  priorite?: number
  portee?: number
  prime_cedee: number
  sinistres_recuperes: number
  solde: number
  statut: 'actif' | 'en_renouvellement' | 'expire'
}

interface ScenarioPML {
  scenario: string
  description: string
  probabilite: string
  sinistre_brut: number
  recuperation_reassurance: number
  charge_nette: number
  impact_fonds_propres: string
  couleur: string
}

// ─── Données démo ──────────────────────────────────────────────────────────

const TRAITES_DEMO: TraiteReassurance[] = [
  {
    type: 'Quote-Part',
    reassureur: 'SCOR SE — Paris',
    quote_part: 40,
    prime_cedee: 48500000,
    sinistres_recuperes: 18200000,
    solde: -30300000,
    statut: 'actif',
  },
  {
    type: 'Excédent de Plein',
    reassureur: 'Munich Re — Munich',
    plein_de_conservation: 25000000,
    prime_cedee: 12800000,
    sinistres_recuperes: 5600000,
    solde: -7200000,
    statut: 'actif',
  },
  {
    type: 'XL Risque (Auto)',
    reassureur: 'Swiss Re — Zurich',
    priorite: 15000000,
    portee: 85000000,
    prime_cedee: 8400000,
    sinistres_recuperes: 0,
    solde: -8400000,
    statut: 'actif',
  },
  {
    type: 'Stop-Loss',
    reassureur: 'Hannover Re — Hanovre',
    priorite: 110,
    portee: 140,
    prime_cedee: 6200000,
    sinistres_recuperes: 0,
    solde: -6200000,
    statut: 'en_renouvellement',
  },
  {
    type: 'XL Événement (Catnat)',
    reassureur: 'AFRICA Re — Abuja',
    priorite: 50000000,
    portee: 200000000,
    prime_cedee: 4100000,
    sinistres_recuperes: 0,
    solde: -4100000,
    statut: 'actif',
  },
]

const SCENARIOS_PML: ScenarioPML[] = [
  {
    scenario: 'Scénario Courant',
    description: 'Sinistralité moyenne — année normale',
    probabilite: '1/1 an',
    sinistre_brut: 85000000,
    recuperation_reassurance: 32000000,
    charge_nette: 53000000,
    impact_fonds_propres: '12%',
    couleur: '#22c55e',
  },
  {
    scenario: 'Scénario Grave',
    description: 'Cumul sinistres importants — crue, grêle',
    probabilite: '1/10 ans',
    sinistre_brut: 220000000,
    recuperation_reassurance: 145000000,
    charge_nette: 75000000,
    impact_fonds_propres: '17%',
    couleur: '#f59e0b',
  },
  {
    scenario: 'Scénario Extrême (PML)',
    description: 'Catastrophe naturelle majeure zone CIMA',
    probabilite: '1/100 ans',
    sinistre_brut: 580000000,
    recuperation_reassurance: 420000000,
    charge_nette: 160000000,
    impact_fonds_propres: '36%',
    couleur: '#ef4444',
  },
]

const BORDEREAU_DEMO = [
  { contrat: 'AUTO-2024-8821', branche: 'Auto', prime_brute: 450000, taux_cession: 40, prime_cedee: 180000, reassureur: 'SCOR SE' },
  { contrat: 'AUTO-2024-8822', branche: 'Auto', prime_brute: 820000, taux_cession: 40, prime_cedee: 328000, reassureur: 'SCOR SE' },
  { contrat: 'IRD-2024-1201', branche: 'Incendie', prime_brute: 2400000, taux_cession: 65, prime_cedee: 1560000, reassureur: 'Munich Re' },
  { contrat: 'IRD-2024-1205', branche: 'Incendie', prime_brute: 1850000, taux_cession: 60, prime_cedee: 1110000, reassureur: 'Munich Re' },
  { contrat: 'VIE-2024-0455', branche: 'Vie', prime_brute: 3200000, taux_cession: 50, prime_cedee: 1600000, reassureur: 'Swiss Re' },
]

const EVOLUTION_REASSURANCE = [
  { trim: 'Q1 23', primes_cedees: 18.2, recup: 4.5, solde: -13.7 },
  { trim: 'Q2 23', primes_cedees: 19.8, recup: 8.2, solde: -11.6 },
  { trim: 'Q3 23', primes_cedees: 21.1, recup: 12.4, solde: -8.7 },
  { trim: 'Q4 23', primes_cedees: 22.5, recup: 6.1, solde: -16.4 },
  { trim: 'Q1 24', primes_cedees: 23.4, recup: 15.8, solde: -7.6 },
  { trim: 'Q2 24', primes_cedees: 24.1, recup: 9.2, solde: -14.9 },
]

const REPARTITION_REASSUREURS = [
  { name: 'SCOR SE', value: 38, color: '#3b82f6' },
  { name: 'Munich Re', value: 26, color: '#8b5cf6' },
  { name: 'Swiss Re', value: 18, color: '#10b981' },
  { name: 'Hannover Re', value: 11, color: '#f59e0b' },
  { name: 'AFRICA Re', value: 7, color: '#ef4444' },
]

// ─── Composant principal ───────────────────────────────────────────────────

export default function ReassurancePage() {
  const [onglet, setOnglet] = useState<'programme' | 'pml' | 'bordereau' | 'c12' | 'documents' | 'correspondances' | 'courtiers' | 'archive' | 'rapports'>('programme')

  const fmt = (n: number) => n.toLocaleString('fr-FR') + ' XAF'
  const fmtM = (n: number) => (n / 1000000).toFixed(1) + 'M XAF'

  const totalPrimeCedee = TRAITES_DEMO.reduce((s, t) => s + t.prime_cedee, 0)
  const totalRecuperee = TRAITES_DEMO.reduce((s, t) => s + t.sinistres_recuperes, 0)
  const tauxCession = 31.2 // % du volume de primes brutes
  const tauxRecuperation = Math.round((totalRecuperee / totalPrimeCedee) * 100)

  const statutBadge = (statut: string) => {
    const cfg: Record<string, { bg: string; label: string }> = {
      actif: { bg: 'bg-green-100 text-green-700', label: 'Actif' },
      en_renouvellement: { bg: 'bg-amber-100 text-amber-700', label: 'En renouvellement' },
      expire: { bg: 'bg-red-100 text-red-600', label: 'Expiré' },
    }
    const c = cfg[statut] || { bg: 'bg-gray-100 text-gray-600', label: statut }
    return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${c.bg}`}>{c.label}</span>
  }

  return (
    <div className="space-y-6">

      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Réassurance</h1>
          <p className="text-sm text-gray-500 mt-1">Programme traités · PML · Bordereau cession · État C12 CIMA</p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 text-sm border border-gray-300 bg-white text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50">
            <DocumentChartBarIcon className="w-4 h-4" />
            État C12
          </button>
          <button className="flex items-center gap-2 text-sm bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
            <ArrowDownTrayIcon className="w-4 h-4" />
            Exporter bordereau
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Primes cédées', value: fmtM(totalPrimeCedee), icon: ArrowTrendingUpIcon, color: 'text-blue-600 bg-blue-50', sub: `Taux cession ${tauxCession}%` },
          { label: 'Récupérations', value: fmtM(totalRecuperee), icon: ShieldCheckIcon, color: 'text-green-600 bg-green-50', sub: `Taux récup. ${tauxRecuperation}%` },
          { label: 'Traités actifs', value: TRAITES_DEMO.filter(t => t.statut === 'actif').length.toString(), icon: DocumentChartBarIcon, color: 'text-primary-600 bg-primary-50', sub: `${TRAITES_DEMO.length} total` },
          { label: 'PML extrême', value: '580M XAF', icon: ExclamationTriangleIcon, color: 'text-red-600 bg-red-50', sub: 'Charge nette 160M' },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="flex items-center gap-3 mb-2">
              <div className={`${k.color} p-2 rounded-lg flex-shrink-0`}>
                <k.icon className="w-5 h-5" />
              </div>
              <p className="text-xs text-gray-500">{k.label}</p>
            </div>
            <p className="text-base font-bold text-gray-900">{k.value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{k.sub}</p>
          </div>
        ))}
      </div>

      {/* Conformité Art. 308 CIMA */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
        <InformationCircleIcon className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-amber-800">Conformité Art. 308 CIMA — Plafond de rétention</p>
          <p className="text-xs text-amber-700 mt-0.5">
            La rétention nette par risque ne doit pas dépasser 10% des fonds propres nets.
            Fonds propres estimés : <strong>450M XAF</strong> → Plafond rétention : <strong>45M XAF/risque</strong>.
            Programme actuel : conforme ✓
          </p>
        </div>
      </div>

      {/* Onglets */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {[
            { key: 'programme', label: 'Programme traités', icon: ShieldCheckIcon },
            { key: 'pml', label: 'Scénarios PML', icon: ExclamationTriangleIcon },
            { key: 'bordereau', label: 'Bordereau cession', icon: DocumentChartBarIcon },
            { key: 'c12', label: 'État C12 CIMA', icon: ChartBarIcon },
            { key: 'documents', label: 'Dématérialisation', icon: DocumentArrowUpIcon },
            { key: 'correspondances', label: 'Correspondances', icon: PencilSquareIcon },
            { key: 'courtiers', label: 'Courtiers', icon: UserGroupIcon },
            { key: 'archive', label: 'Archive', icon: FolderOpenIcon },
            { key: 'rapports', label: 'Rapports', icon: ChartBarIcon },
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

      {/* ── Programme traités ──────────────────────────────────────────── */}
      {onglet === 'programme' && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          <div className="xl:col-span-2 space-y-4">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200">
                <h3 className="text-sm font-semibold text-gray-800">Traités en vigueur</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Type</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Réassureur</th>
                      <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Conditions</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Prime cédée</th>
                      <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Récupérations</th>
                      <th className="text-center px-4 py-2.5 text-xs font-medium text-gray-600">Statut</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {TRAITES_DEMO.map((t, i) => (
                      <tr key={i} className={`${i % 2 === 0 ? '' : 'bg-gray-50'} hover:bg-blue-50 transition-colors`}>
                        <td className="px-4 py-3">
                          <p className="font-medium text-gray-800">{t.type}</p>
                        </td>
                        <td className="px-4 py-3 text-gray-600 text-xs">{t.reassureur}</td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {t.quote_part != null && `Quote-part ${t.quote_part}%`}
                          {t.plein_de_conservation != null && `Conservation ${fmtM(t.plein_de_conservation)}`}
                          {t.priorite != null && t.portee != null && t.portee < 300 && `Priorité ${t.priorite}% / Portée ${t.portee}%`}
                          {t.priorite != null && t.portee != null && t.portee >= 300 && `Priorité ${fmtM(t.priorite)} / Portée ${fmtM(t.portee)}`}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-900">{fmt(t.prime_cedee)}</td>
                        <td className="px-4 py-3 text-right font-mono text-green-600">
                          {t.sinistres_recuperes > 0 ? fmt(t.sinistres_recuperes) : '—'}
                        </td>
                        <td className="px-4 py-3 text-center">{statutBadge(t.statut)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-gray-100 border-t-2 border-gray-300">
                    <tr>
                      <td colSpan={3} className="px-4 py-2.5 font-semibold text-gray-700">TOTAL</td>
                      <td className="px-4 py-2.5 text-right font-bold text-gray-900 font-mono">{fmt(totalPrimeCedee)}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-green-600 font-mono">{fmt(totalRecuperee)}</td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* Évolution primes / récupérations */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-4">Évolution primes cédées vs récupérations (M XAF)</h3>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={EVOLUTION_REASSURANCE}>
                  <defs>
                    <linearGradient id="gradPrimes" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="gradRecup" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="trim" tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={v => v + 'M'} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v: number) => `${v}M XAF`} />
                  <Legend />
                  <Area type="monotone" dataKey="primes_cedees" stroke="#3b82f6" fill="url(#gradPrimes)" strokeWidth={2} name="Primes cédées" />
                  <Area type="monotone" dataKey="recup" stroke="#22c55e" fill="url(#gradRecup)" strokeWidth={2} name="Récupérations" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Répartition réassureurs */}
          <div className="space-y-4">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-4">Répartition par réassureur</h3>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={REPARTITION_REASSUREURS} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
                    {REPARTITION_REASSUREURS.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => `${v}%`} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {REPARTITION_REASSUREURS.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: r.color }} />
                    <span className="flex-1 text-gray-600">{r.name}</span>
                    <span className="font-semibold text-gray-800">{r.value}%</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Analyse IA */}
            <div className="bg-gradient-to-br from-primary-50 to-indigo-50 border border-primary-200 rounded-xl p-4">
              <p className="text-xs font-semibold text-primary-700 mb-2">Analyse IA du programme</p>
              <div className="space-y-2 text-xs text-gray-700">
                <p>✓ Programme conforme Art. 308 CIMA — rétentions dans les limites réglementaires</p>
                <p>⚠ Concentration SCOR SE à 38% — envisager diversification vers AFRICA Re</p>
                <p>✓ Couverture catnat XL Event suffisante pour zone CEMAC (200M XAF)</p>
                <p>ℹ Stop-Loss en renouvellement — finaliser avant le 30/06/2024</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Scénarios PML ──────────────────────────────────────────────── */}
      {onglet === 'pml' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {SCENARIOS_PML.map((s, i) => (
              <div key={i} className="bg-white rounded-xl border-2 shadow-sm p-5" style={{ borderColor: s.couleur }}>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold text-gray-800">{s.scenario}</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full text-white font-medium" style={{ backgroundColor: s.couleur }}>
                    {s.probabilite}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mb-4">{s.description}</p>

                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-gray-400 mb-0.5">Sinistre brut estimé</p>
                    <p className="text-base font-bold text-gray-900">{fmtM(s.sinistre_brut)}</p>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Récupération réassurance</span>
                    <span className="text-green-600 font-semibold">{fmtM(s.recuperation_reassurance)}</span>
                  </div>
                  <div className="border-t border-gray-100 pt-2 flex justify-between text-sm">
                    <span className="font-semibold text-gray-700">Charge nette</span>
                    <span className="font-bold" style={{ color: s.couleur }}>{fmtM(s.charge_nette)}</span>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-2 text-center">
                    <p className="text-xs text-gray-500">Impact fonds propres</p>
                    <p className="text-xl font-black mt-0.5" style={{ color: s.couleur }}>{s.impact_fonds_propres}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Visualisation comparative */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">Comparaison scénarios — Sinistre brut vs Charge nette (M XAF)</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={SCENARIOS_PML.map(s => ({
                scenario: s.scenario.replace('Scénario ', ''),
                brut: Math.round(s.sinistre_brut / 1000000),
                recuperation: Math.round(s.recuperation_reassurance / 1000000),
                net: Math.round(s.charge_nette / 1000000),
              }))} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="scenario" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={v => v + 'M'} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v: number) => `${v}M XAF`} />
                <Legend />
                <Bar dataKey="brut" fill="#94a3b8" name="Sinistre brut" radius={[4, 4, 0, 0]} />
                <Bar dataKey="recuperation" fill="#22c55e" name="Récupération réassur." radius={[4, 4, 0, 0]} />
                <Bar dataKey="net" fill="#ef4444" name="Charge nette" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── Bordereau de cession ───────────────────────────────────────── */}
      {onglet === 'bordereau' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Bordereau de cession — T1 2024</h3>
              <p className="text-xs text-gray-500 mt-0.5">Art. 312 CIMA — Transmission trimestrielle obligatoire</p>
            </div>
            <button className="flex items-center gap-2 text-xs border border-gray-300 rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-50">
              <ArrowDownTrayIcon className="w-4 h-4" />
              Export Excel
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">N° Contrat</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Branche</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Prime brute</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Taux cession</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-gray-600">Prime cédée</th>
                  <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-600">Réassureur</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {BORDEREAU_DEMO.map((b, i) => (
                  <tr key={i} className={i % 2 === 0 ? '' : 'bg-gray-50'}>
                    <td className="px-4 py-2.5 font-mono text-gray-700 text-xs">{b.contrat}</td>
                    <td className="px-4 py-2.5 text-gray-600">{b.branche}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-gray-900">{fmt(b.prime_brute)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-700">{b.taux_cession}%</td>
                    <td className="px-4 py-2.5 text-right font-mono font-semibold text-blue-700">{fmt(b.prime_cedee)}</td>
                    <td className="px-4 py-2.5 text-gray-600 text-xs">{b.reassureur}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-primary-50 border-t-2 border-primary-200">
                <tr>
                  <td colSpan={2} className="px-4 py-2.5 font-semibold text-primary-700">TOTAL T1 2024</td>
                  <td className="px-4 py-2.5 text-right font-bold text-primary-700 font-mono">{fmt(BORDEREAU_DEMO.reduce((s, b) => s + b.prime_brute, 0))}</td>
                  <td className="px-4 py-2.5 text-right text-primary-600">—</td>
                  <td className="px-4 py-2.5 text-right font-bold text-primary-700 font-mono">{fmt(BORDEREAU_DEMO.reduce((s, b) => s + b.prime_cedee, 0))}</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}

      {/* ── État C12 CIMA ─────────────────────────────────────────────── */}
      {onglet === 'c12' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-gray-900">État C12 — Cessions en réassurance</h3>
                <p className="text-xs text-gray-500 mt-0.5">Code CIMA Art. 395-5 · Exercice 2024</p>
              </div>
              <button className="flex items-center gap-2 text-sm bg-primary-600 text-white px-3 py-2 rounded-lg hover:bg-primary-700">
                <ArrowDownTrayIcon className="w-4 h-4" />
                Générer C12 PDF
              </button>
            </div>

            {/* Tableau C12 */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs border border-gray-300">
                <thead>
                  <tr className="bg-primary-700 text-white">
                    <th className="px-3 py-2 text-left border border-primary-600" rowSpan={2}>Branche</th>
                    <th className="px-3 py-2 text-center border border-primary-600" colSpan={3}>Affaires directes</th>
                    <th className="px-3 py-2 text-center border border-primary-600" colSpan={2}>Cessions</th>
                    <th className="px-3 py-2 text-center border border-primary-600" colSpan={2}>Acceptations</th>
                    <th className="px-3 py-2 text-center border border-primary-600" rowSpan={2}>Solde net</th>
                  </tr>
                  <tr className="bg-primary-600 text-white">
                    <th className="px-3 py-2 border border-primary-500">Primes émises</th>
                    <th className="px-3 py-2 border border-primary-500">Sinistres</th>
                    <th className="px-3 py-2 border border-primary-500">S/P%</th>
                    <th className="px-3 py-2 border border-primary-500">Primes cédées</th>
                    <th className="px-3 py-2 border border-primary-500">Récupérations</th>
                    <th className="px-3 py-2 border border-primary-500">Primes acceptées</th>
                    <th className="px-3 py-2 border border-primary-500">Sinistres acceptés</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Auto (B10)', '125,400', '52,100', '41.5%', '50,160', '20,840', '0', '0', '74,900'],
                    ['Incendie (B20)', '48,200', '18,500', '38.4%', '32,300', '12,100', '0', '0', '28,300'],
                    ['RC (B30)', '22,800', '9,200', '40.4%', '9,120', '3,600', '0', '0', '17,280'],
                    ['Transport (B50)', '18,600', '6,800', '36.6%', '7,440', '2,720', '0', '0', '13,880'],
                    ['Vie (B70)', '85,200', '31,400', '36.9%', '42,600', '15,700', '0', '0', '57,300'],
                    ['Maladie (B80)', '34,100', '18,900', '55.4%', '13,640', '7,560', '0', '0', '22,020'],
                  ].map((row, i) => (
                    <tr key={i} className={`${i % 2 === 0 ? 'bg-white' : 'bg-gray-50'} hover:bg-blue-50`}>
                      {row.map((cell, j) => (
                        <td key={j} className={`px-3 py-2 border border-gray-200 ${j > 0 ? 'text-right font-mono' : 'font-medium text-gray-700'} ${j === row.length - 1 ? 'text-primary-700 font-bold' : 'text-gray-800'}`}>
                          {j > 0 && j !== 3 ? cell + ' k' : cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800 text-white font-bold">
                    <td className="px-3 py-2 border border-gray-700">TOTAL</td>
                    <td className="px-3 py-2 border border-gray-700 text-right font-mono">334,300 k</td>
                    <td className="px-3 py-2 border border-gray-700 text-right font-mono">136,900 k</td>
                    <td className="px-3 py-2 border border-gray-700 text-right">40.9%</td>
                    <td className="px-3 py-2 border border-gray-700 text-right font-mono">155,260 k</td>
                    <td className="px-3 py-2 border border-gray-700 text-right font-mono">62,520 k</td>
                    <td className="px-3 py-2 border border-gray-700 text-right">—</td>
                    <td className="px-3 py-2 border border-gray-700 text-right">—</td>
                    <td className="px-3 py-2 border border-gray-700 text-right font-mono">213,680 k</td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <p className="text-xs text-gray-400 mt-3">* Montants en milliers XAF (kXAF) · Conformément au modèle C12 CRCA/CIMA · Transmission annuelle avant le 30/06</p>
          </div>
        </div>
      )}

      {/* ── Dématérialisation ─────────────────────────────────────────── */}
      {onglet === 'documents' && (
        <div className="space-y-6">

          {/* Traités numériques */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
              <BuildingLibraryIcon className="h-5 w-5 text-teal-600" />
              Traités de réassurance — Gestion documentaire numérique
            </h3>
            <p className="text-xs text-gray-500 mb-4">Upload et archivage des slips, notes de couverture, traités, avenants et correspondances avec les réassureurs.</p>
            <div className="grid grid-cols-4 gap-3 mb-4">
              {[
                { label: 'Traités actifs', value: '4', cls: 'bg-teal-50 border-teal-200 text-teal-700' },
                { label: 'En renouvellement', value: '1', cls: 'bg-amber-50 border-amber-200 text-amber-700' },
                { label: 'Documents numérisés', value: '28', cls: 'bg-blue-50 border-blue-200 text-blue-700' },
                { label: 'Taux numérisation', value: '92%', cls: 'bg-green-50 border-green-200 text-green-700' },
              ].map((k, i) => (
                <div key={i} className={`border rounded-xl p-4 text-center ${k.cls}`}>
                  <p className="text-2xl font-bold">{k.value}</p>
                  <p className="text-xs mt-0.5">{k.label}</p>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    {['Réassureur', 'Type traité', 'Documents numérisés', 'Statut', 'Actions'].map(h => (
                      <th key={h} className="text-left py-2 px-4 text-xs font-semibold text-gray-500 uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {[
                    { rea: 'SCOR SE — Paris',          type: 'Quote-Part',      docs: 8, statut: 'actif',           docs_list: ['Traité signé 2026', 'Avenant n°1', 'Note de couverture', 'Bordereau Q1 2026'] },
                    { rea: 'Munich Re — Munich',        type: 'Excédent de Plein', docs: 6, statut: 'actif',       docs_list: ['Traité 2026', 'Slip placement', 'Bordereau sinistres'] },
                    { rea: 'Swiss Re — Zurich',         type: 'XL Risque Auto',  docs: 7, statut: 'actif',          docs_list: ['Traité XL 2026', 'Note de couverture', 'Tableau primes'] },
                    { rea: 'Hannover Re — Hanovre',     type: 'Stop-Loss',       docs: 4, statut: 'en_renouvellement', docs_list: ['Traité expirant', 'Offre renouvellement 2027'] },
                    { rea: 'AFRICA Re — Abuja',         type: 'XL Catnat',       docs: 3, statut: 'actif',          docs_list: ['Traité Catnat 2026', 'Note de couverture'] },
                  ].map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50 transition-colors">
                      <td className="py-3 px-4 font-medium text-gray-900">{r.rea}</td>
                      <td className="py-3 px-4 text-gray-500">{r.type}</td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {r.docs_list.slice(0, 2).map((d, j) => (
                            <span key={j} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded flex items-center gap-1">
                              <DocumentArrowUpIcon className="h-2.5 w-2.5" />{d}
                            </span>
                          ))}
                          {r.docs_list.length > 2 && <span className="text-xs text-gray-400">+{r.docs_list.length - 2}</span>}
                        </div>
                        <span className="text-xs text-gray-400 mt-1 block">{r.docs} documents</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${r.statut === 'actif' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                          {r.statut === 'actif' ? 'Actif' : 'En renouvellement'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex gap-2">
                          <button className="text-xs text-primary-600 hover:underline">Voir docs</button>
                          <button className="text-xs text-gray-400 hover:text-gray-600">Ajouter</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Bordereaux électroniques */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
              <DocumentChartBarIcon className="h-5 w-5 text-blue-600" />
              Bordereaux électroniques — Échanges avec les réassureurs
            </h3>
            <p className="text-xs text-gray-500 mb-4">Bordereaux de primes et de sinistres générés automatiquement et transmis numériquement aux réassureurs.</p>
            <div className="space-y-3">
              {[
                { ref: 'BORD-PRIMES-Q1-2026', type: 'Bordereau de primes', reassureur: 'SCOR SE', montant: '48.5M XAF', statut: 'transmis', date: '2026-04-02', accuse: true },
                { ref: 'BORD-SIN-Q1-2026', type: 'Bordereau de sinistres', reassureur: 'SCOR SE', montant: '18.2M XAF', statut: 'transmis', date: '2026-04-03', accuse: true },
                { ref: 'BORD-PRIMES-Q1-MUNRE', type: 'Bordereau de primes', reassureur: 'Munich Re', montant: '12.8M XAF', statut: 'transmis', date: '2026-04-04', accuse: false },
                { ref: 'BORD-SIN-Q1-SWRE', type: 'Bordereau de sinistres', reassureur: 'Swiss Re', montant: '0 XAF', statut: 'en_preparation', date: '—', accuse: false },
              ].map((b, i) => (
                <div key={i} className="flex items-center gap-4 p-3 border border-gray-100 rounded-xl hover:bg-gray-50 transition-colors">
                  <DocumentChartBarIcon className="h-8 w-8 text-blue-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-900">{b.ref}</p>
                    <p className="text-xs text-gray-500">{b.type} · {b.reassureur} · {b.date}</p>
                  </div>
                  <p className="text-sm font-bold text-gray-900">{b.montant}</p>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${b.statut === 'transmis' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                      {b.statut === 'transmis' ? 'Transmis' : 'En préparation'}
                    </span>
                    {b.accuse && (
                      <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                        <CheckCircleIcon className="h-3 w-3" /> Accusé reçu
                      </span>
                    )}
                    {!b.accuse && b.statut === 'transmis' && (
                      <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
                        <ClockIcon className="h-3 w-3" /> En attente accusé
                      </span>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button className="p-1.5 text-gray-400 hover:text-primary-600 transition-colors" title="Télécharger">
                      <ArrowDownTrayIcon className="h-4 w-4" />
                    </button>
                    {b.statut === 'transmis' && (
                      <button className="p-1.5 text-gray-400 hover:text-green-600 transition-colors" title="Envoyer par email">
                        <EnvelopeIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Zone upload traité */}
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
            <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <DocumentArrowUpIcon className="h-4 w-4 text-primary-600" />
              Ajouter un document de réassurance
            </h4>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <select className="px-3 py-2 border border-gray-300 rounded-lg text-sm">
                <option>Réassureur…</option>
                {['SCOR SE', 'Munich Re', 'Swiss Re', 'Hannover Re', 'AFRICA Re'].map(r => <option key={r}>{r}</option>)}
              </select>
              <select className="px-3 py-2 border border-gray-300 rounded-lg text-sm">
                <option>Type de document</option>
                {['Traité signé', 'Avenant', 'Note de couverture', 'Slip placement', 'Bordereau primes', 'Bordereau sinistres', 'Correspondance', 'Autre'].map(t => <option key={t}>{t}</option>)}
              </select>
              <input className="px-3 py-2 border border-gray-300 rounded-lg text-sm" placeholder="Référence / millésime…" />
            </div>
            <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-primary-400 hover:bg-primary-50 transition-colors cursor-pointer">
              <DocumentArrowUpIcon className="h-10 w-10 text-gray-400 mx-auto mb-2" />
              <p className="text-sm font-medium text-gray-700">Glissez le document ici ou cliquez</p>
              <p className="text-xs text-gray-400 mt-1">PDF, DOCX, XLSX — max 50 Mo</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Onglet Correspondances ───────────────────────────────────── */}
      {onglet === 'correspondances' && (
        <CorrespondancesModule
          module="reassurance"
          titre="Correspondances — Réassurance"
          references={TRAITES_DEMO.map(t => ({ value: t.reassureur, label: `${t.type} — ${t.reassureur}` }))}
        />
      )}

      {/* ── Onglet Courtiers ─────────────────────────────────────────── */}
      {onglet === 'courtiers' && (
        <div className="max-w-3xl">
          <OngletCourtiers />
        </div>
      )}

      {/* ── Archive réassurance ──────────────────────────────────────── */}
      {onglet === 'archive' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FolderOpenIcon className="h-5 w-5 text-primary-600" />
            Archive numérique — Réassurance
          </h3>
          <ArchiveNumerique module="reassurance" hauteurMax="500px" />
        </div>
      )}

      {/* ── Rapports réassurance ─────────────────────────────────────── */}
      {onglet === 'rapports' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <RapportsModule module="reassurance" />
        </div>
      )}
    </div>
  )
}
