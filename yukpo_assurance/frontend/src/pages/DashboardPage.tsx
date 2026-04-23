import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import {
  BanknotesIcon,
  ShieldCheckIcon,
  ChartBarIcon,
  DocumentCheckIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon,
  ArrowUpTrayIcon,
} from '@heroicons/react/24/outline'
import { KPICard } from '../components/KPICard'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { EmptyState } from '../components/EmptyState'
import { useDashboard } from '../hooks/useDashboard'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'
import { AlerteCIMA } from '../api/types'
import { useNavigate } from 'react-router-dom'

const COLORS = ['#0054A6', '#00B0F0', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

function formatMontant(val: number): string {
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)} Mrd`
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)} M`
  if (val >= 1_000) return `${(val / 1_000).toFixed(0)} K`
  return `${val}`
}

const ALERTE_STYLES = {
  error:   { bg: 'bg-red-50 border-red-200',    icon: 'text-red-500',    text: 'text-red-800',    Icon: XCircleIcon,              label: 'Erreur' },
  warning: { bg: 'bg-yellow-50 border-yellow-200', icon: 'text-yellow-600', text: 'text-yellow-800', Icon: ExclamationTriangleIcon, label: 'Avertissement' },
  info:    { bg: 'bg-blue-50 border-blue-200',  icon: 'text-blue-500',   text: 'text-blue-800',   Icon: InformationCircleIcon,   label: 'Information' },
} as const

function AlerteItem({ alerte }: { alerte: AlerteCIMA }) {
  const s = ALERTE_STYLES[alerte.type]
  const Icon = s.Icon

  return (
    <div className={`flex gap-2 items-start p-3 rounded-lg border ${s.bg}`} role="alert">
      <Icon className={`h-4 w-4 flex-shrink-0 mt-0.5 ${s.icon}`} aria-label={s.label} />
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${s.text}`}>{alerte.message}</p>
        {alerte.echeance && (
          <p className="text-xs text-gray-500 mt-0.5">Échéance : {alerte.echeance}</p>
        )}
      </div>
    </div>
  )
}

export function DashboardPage() {
  const { data, isLoading, error, lastUpdated, refresh } = useDashboard(2025)
  const navigate = useNavigate()

  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" label="Chargement du tableau de bord..." />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <ExclamationTriangleIcon className="h-12 w-12 text-red-400" />
        <p className="text-gray-600">{error}</p>
        <button
          onClick={refresh}
          className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700 transition-colors"
        >
          Réessayer
        </button>
      </div>
    )
  }

  const hasKpis = data?.primes_nettes != null
  const kpis = hasKpis
    ? {
        primes_nettes: data!.primes_nettes!,
        ratio_sp: data!.ratio_sp ?? 0,
        marge_solvabilite: data!.marge_solvabilite ?? 0,
        polices_actives: data!.polices_actives ?? 0,
      }
    : null

  const primesParBranche = data?.primes_par_branche ?? []
  const repartitionCharges = data?.repartition_charges ?? []
  const alertes = data?.alertes_cima ?? []

  if (!hasKpis && !primesParBranche.length && !alertes.length) {
    return (
      <div className="p-6">
        <header className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">Tableau de bord 2025</h1>
        </header>
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm">
          <EmptyState
            icon={<ChartBarIcon className="h-12 w-12" />}
            title="Aucune donnée disponible"
            description="Importez votre portefeuille CIMA ou connectez votre source de données pour voir vos indicateurs."
            action={
              <div className="flex gap-2">
                <button
                  onClick={() => navigate('/documents')}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors"
                >
                  <ArrowUpTrayIcon className="h-4 w-4" />
                  Importer des données
                </button>
                <button
                  onClick={refresh}
                  disabled={isLoading}
                  aria-busy={isLoading}
                  className="inline-flex items-center gap-1.5 px-4 py-2 border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  <ArrowPathIcon className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                  Actualiser
                </button>
              </div>
            }
          />
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Tableau de bord 2025</h1>
          {lastUpdated && (
            <p className="text-xs text-gray-400 mt-0.5">
              Mis à jour {format(lastUpdated, "HH:mm 'le' d MMM", { locale: fr })}
            </p>
          )}
        </div>
        <button
          onClick={refresh}
          disabled={isLoading}
          aria-busy={isLoading}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowPathIcon className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Actualiser
        </button>
      </header>

      {/* KPI Cards */}
      {kpis && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <KPICard
            title="Primes nettes"
            value={formatMontant(kpis.primes_nettes)}
            subtitle="FCFA — exercice 2025"
            icon={<BanknotesIcon className="h-6 w-6" />}
            trend={{ value: 8.3, label: 'vs 2024' }}
            color="blue"
          />
          <KPICard
            title="Ratio S/P"
            value={`${kpis.ratio_sp.toFixed(1)}%`}
            subtitle="Sinistres / Primes"
            icon={<ChartBarIcon className="h-6 w-6" />}
            trend={{ value: -2.1, label: 'vs 2024' }}
            color="orange"
          />
          <KPICard
            title="Marge de solvabilité"
            value={`${kpis.marge_solvabilite.toFixed(1)}%`}
            subtitle="Exigence CIMA : 100%"
            icon={<ShieldCheckIcon className="h-6 w-6" />}
            trend={{ value: 5.7, label: 'vs 2024' }}
            color="green"
          />
          <KPICard
            title="Polices actives"
            value={kpis.polices_actives.toLocaleString('fr-FR')}
            subtitle="Portefeuille en vigueur"
            icon={<DocumentCheckIcon className="h-6 w-6" />}
            trend={{ value: 12.4, label: 'vs 2024' }}
            color="purple"
          />
        </div>
      )}

      {/* Charts row */}
      {(primesParBranche.length > 0 || repartitionCharges.length > 0) && (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {primesParBranche.length > 0 && (
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Primes et sinistres par branche (FCFA)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={primesParBranche} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="branche" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => formatMontant(v)} width={60} />
              <Tooltip
                formatter={(value: number) => [formatMontant(value), '']}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: 12 }}
              />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="primes" name="Primes" fill="#0054A6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="sinistres" name="Sinistres" fill="#00B0F0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        )}

        {repartitionCharges.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Répartition des charges</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={repartitionCharges}
                dataKey="pourcentage"
                nameKey="categorie"
                cx="50%"
                cy="50%"
                outerRadius={75}
                innerRadius={40}
              >
                {repartitionCharges.map((_, index) => (
                  <Cell key={index} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => [`${value}%`, '']}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: 12 }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">
            {repartitionCharges.map((item, i) => (
              <div key={item.categorie} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                    style={{ backgroundColor: COLORS[i % COLORS.length] }}
                  />
                  <span className="text-gray-600">{item.categorie}</span>
                </div>
                <span className="font-medium text-gray-700">{item.pourcentage}%</span>
              </div>
            ))}
          </div>
        </div>
        )}
      </div>
      )}

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Alertes CIMA */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <ExclamationTriangleIcon className="h-5 w-5 text-yellow-500" />
            <h3 className="text-sm font-semibold text-gray-700">Alertes CIMA</h3>
            <span className="ml-auto text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
              {alertes.length}
            </span>
          </div>
          {alertes.length > 0 ? (
            <div className="space-y-2">
              {alertes.map((alerte) => (
                <AlerteItem key={alerte.id} alerte={alerte} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500 py-4 text-center">Aucune alerte CIMA en cours.</p>
          )}
        </div>

        {/* Narrative IA */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <InformationCircleIcon className="h-5 w-5 text-primary-600" />
            <h3 className="text-sm font-semibold text-gray-700">Analyse YukpoPro</h3>
            <span className="ml-auto text-xs text-gray-400"></span>
          </div>
          <div className="text-sm text-gray-600 leading-relaxed">
            {data?.narrative_ia ? (
              <p>{data.narrative_ia}</p>
            ) : (
              <p className="text-xs text-gray-400 italic">
                L'analyse IA sera générée dès que les données d'exercice seront disponibles.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
