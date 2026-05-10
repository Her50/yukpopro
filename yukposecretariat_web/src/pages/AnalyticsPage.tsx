/**
 * Phase 5b — Page Analytics & Insights (responsive mobile + i18n).
 *
 * Dashboard direction marketing/com :
 *   - KPIs résumé exécutif (8 cards)
 *   - Top modules (graphique barres)
 *   - Top types_doc (Designer Pro)
 *   - Top users
 *   - Coûts par jour (timeline)
 *   - Quality metrics (latency p95/p99 par endpoint)
 *
 * Accès : roles admin/dg/daf/manager (le backend bloque sinon).
 * Responsive : mobile-first Tailwind, breakpoints sm/md/lg.
 * i18n : toutes clés FR via t('analytics.xxx', 'fallback FR').
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Loader2, TrendingUp, Users, FileText, DollarSign, Sparkles, Activity } from 'lucide-react'
import { bureauAnalyticsAPI } from '../api/client'

const PERIODES = [7, 30, 90, 365] as const

function KpiCard({ icon: Icon, label, value, suffix }: {
  icon: any, label: string, value: number | string, suffix?: string,
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-3 sm:p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={14} className="text-amber-600" />
        <span className="text-[10px] sm:text-xs text-gray-500 font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <div className="text-lg sm:text-2xl font-bold text-gray-900 tabular-nums">
        {typeof value === 'number' ? value.toLocaleString() : value}
        {suffix && <span className="text-xs text-gray-500 ml-1">{suffix}</span>}
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const { t } = useTranslation()
  const [days, setDays] = useState<number>(30)

  const { data: dashboard, isLoading: loadingDash } = useQuery<any>({
    queryKey: ['bureau-analytics-dashboard', days],
    queryFn: () => bureauAnalyticsAPI.dashboard(days).then(r => r.data),
    staleTime: 60_000,
  })
  const { data: cost } = useQuery<any>({
    queryKey: ['bureau-analytics-cost', days],
    queryFn: () => bureauAnalyticsAPI.cost(days).then(r => r.data),
    staleTime: 60_000,
  })
  const { data: templates } = useQuery<any>({
    queryKey: ['bureau-analytics-templates', days],
    queryFn: () => bureauAnalyticsAPI.templates(days, 10).then(r => r.data),
    staleTime: 60_000,
  })
  const { data: users } = useQuery<any>({
    queryKey: ['bureau-analytics-users', days],
    queryFn: () => bureauAnalyticsAPI.topUsers(days, 10).then(r => r.data),
    staleTime: 60_000,
  })

  const kpis = dashboard?.kpis || {}

  if (loadingDash) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        <Loader2 size={20} className="animate-spin mr-2" />
        {t('analytics.loading', 'Chargement du tableau de bord…')}
      </div>
    )
  }

  if (dashboard?.vide) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-center text-gray-600">
        <Activity size={32} className="mx-auto text-gray-300 mb-3" />
        <p className="text-sm font-semibold">{t('analytics.empty', 'Aucune donnée pour cette période')}</p>
        <p className="text-xs text-gray-500 mt-1">
          {t('analytics.emptyHint', "Génère quelques visuels ou documents puis reviens ici.")}
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto p-3 sm:p-5 space-y-4 sm:space-y-5">
      {/* En-tête + filtre période */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-lg sm:text-xl font-bold text-gray-900 flex items-center gap-2">
            <TrendingUp size={18} className="text-amber-600" />
            {t('analytics.title', 'Tableau de bord — Analytics')}
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {t('analytics.subtitle', 'Usage, coûts, top templates et utilisateurs de votre organisation')}
          </p>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1 self-start sm:self-auto">
          {PERIODES.map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`text-xs px-2 sm:px-3 py-1.5 rounded-lg font-semibold transition-all ${
                days === d ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-900'
              }`}>
              {d === 365 ? '1 an' : `${d}j`}
            </button>
          ))}
        </div>
      </div>

      {/* KPIs grid responsive : 2 cols mobile / 4 cols desktop */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3">
        <KpiCard icon={Activity} label={t('analytics.kpiCalls', 'Appels LLM')}
          value={kpis.nb_appels_llm || 0} />
        <KpiCard icon={FileText} label={t('analytics.kpiDocs', 'Documents générés')}
          value={kpis.nb_documents_generes || 0} />
        <KpiCard icon={DollarSign} label={t('analytics.kpiFcfa', 'FCFA consommés')}
          value={Math.round(kpis.fcfa_consommes || 0)} />
        <KpiCard icon={Sparkles} label={t('analytics.kpiCredits', 'Crédits Yukpo')}
          value={Math.round(kpis.credits_consommes || 0)} />
        <KpiCard icon={Users} label={t('analytics.kpiUsers', 'Utilisateurs actifs')}
          value={kpis.nb_users_actifs || 0} />
        <KpiCard icon={Activity} label={t('analytics.kpiAvgDocs', 'Docs / jour')}
          value={kpis.moyenne_docs_par_jour || 0} />
        <KpiCard icon={DollarSign} label={t('analytics.kpiAvgCost', 'Crédits / jour')}
          value={Math.round(kpis.moyenne_credits_par_jour || 0)} />
        <KpiCard icon={TrendingUp} label={t('analytics.kpiPeriod', 'Période')}
          value={`${days}j`} />
      </div>

      {/* Top modules + Top types_doc — grille 1 col mobile / 2 cols desktop */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
        <div className="bg-white rounded-2xl border border-gray-200 p-3 sm:p-4">
          <p className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-1.5">
            <Activity size={14} className="text-amber-600" />
            {t('analytics.topModules', 'Top modules')}
          </p>
          {(dashboard?.top_modules || []).length === 0 ? (
            <p className="text-xs text-gray-400">{t('analytics.noData', 'Aucune donnée')}</p>
          ) : (
            <div className="space-y-1.5">
              {(dashboard?.top_modules || []).map((m: any, i: number) => {
                const max = Math.max(...(dashboard.top_modules || []).map((x: any) => x.nb_appels)) || 1
                const pct = (m.nb_appels / max) * 100
                return (
                  <div key={i} className="text-xs">
                    <div className="flex justify-between text-gray-700 font-medium mb-0.5">
                      <span className="truncate">{m.module}</span>
                      <span className="tabular-nums">{m.nb_appels} · {Math.round(m.credits)} cr</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-amber-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-3 sm:p-4">
          <p className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-1.5">
            <FileText size={14} className="text-amber-600" />
            {t('analytics.topTemplates', 'Top documents générés')}
          </p>
          {(templates?.top || []).length === 0 ? (
            <p className="text-xs text-gray-400">{t('analytics.noData', 'Aucune donnée')}</p>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {(templates?.top || []).map((tp: any, i: number) => (
                <div key={i} className="flex justify-between items-center py-1 border-b border-gray-50 text-xs">
                  <span className="text-gray-700 truncate">{tp.type_doc}</span>
                  <span className="text-gray-500 tabular-nums shrink-0 ml-2">
                    {tp.nb_generes} · {Math.round(tp.cout_fcfa_total).toLocaleString()} F
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Top users + Coûts par jour */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
        <div className="bg-white rounded-2xl border border-gray-200 p-3 sm:p-4">
          <p className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-1.5">
            <Users size={14} className="text-amber-600" />
            {t('analytics.topUsers', 'Top utilisateurs')}
          </p>
          {(users?.top || []).length === 0 ? (
            <p className="text-xs text-gray-400">{t('analytics.noData', 'Aucune donnée')}</p>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {(users?.top || []).map((u: any) => (
                <div key={u.user_id} className="flex justify-between items-center py-1 border-b border-gray-50 text-xs">
                  <span className="text-gray-700 truncate">{u.nom} <span className="text-gray-400 text-[10px]">#{u.user_id}</span></span>
                  <span className="text-gray-500 tabular-nums shrink-0 ml-2">
                    {u.nb_appels} · {Math.round(u.fcfa_total).toLocaleString()} F
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-3 sm:p-4">
          <p className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-1.5">
            <DollarSign size={14} className="text-amber-600" />
            {t('analytics.costPerDay', 'Coûts par jour (FCFA)')}
          </p>
          {(cost?.par_jour || []).length === 0 ? (
            <p className="text-xs text-gray-400">{t('analytics.noData', 'Aucune donnée')}</p>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {(cost?.par_jour || []).slice(-15).map((j: any) => {
                const max = Math.max(...(cost?.par_jour || []).map((x: any) => x.fcfa)) || 1
                const pct = (j.fcfa / max) * 100
                return (
                  <div key={j.jour} className="text-xs">
                    <div className="flex justify-between text-gray-700 mb-0.5">
                      <span className="font-medium">{j.jour}</span>
                      <span className="tabular-nums">{Math.round(j.fcfa).toLocaleString()} F</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
