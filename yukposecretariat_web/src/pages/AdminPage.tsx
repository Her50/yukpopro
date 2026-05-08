import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Shield, Users, Search, X, Loader2, Plus, Lock, Unlock, TrendingUp,
  Wallet, BarChart3, Eye, AlertCircle, Megaphone, LayoutDashboard,
  DollarSign, ArrowUpRight, ArrowDownRight, Calendar,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { adminAPI } from '../api/client'
import { useAuth } from '../context/AuthContext'

const ADMIN_ROLES = ['admin', 'super_admin', 'yukpo_owner']

const MODULE_LABEL_KEYS: Record<string, string> = {
  redaction:    'abonnement.modLabelRedaction',
  ocr:          'abonnement.modLabelOcr',
  audio:        'abonnement.modLabelAudio',
  traduction:   'abonnement.modLabelTraduction',
  infographie:  'abonnement.modLabelInfographie',
  designerpro:  'abonnement.modLabelDesignerPro',
  gestion:      'admin.modLabelGestionShort',
  documents:    'abonnement.modLabelDocuments',
  bureau:       'abonnement.modLabelBureau',
  inconnu:      'abonnement.modLabelOther',
}

function fmtFcfa(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('fr-FR') + ' FCFA'
}
function fmtNb(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('fr-FR')
}
function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('fr-FR', {
      day: '2-digit', month: 'short', year: 'numeric',
      ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
    })
  } catch { return '—' }
}

export default function AdminPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'overview' | 'utilisateurs' | 'revenus' | 'promotions'>('overview')
  const [recherche, setRecherche] = useState('')
  const [page, setPage] = useState(1)
  const [userOuvert, setUserOuvert] = useState<number | null>(null)

  // Garde rôle
  if (user && !ADMIN_ROLES.includes(user.role)) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          <AlertCircle className="inline mr-2" size={14} />
          {t('admin.denied', { role: user.role })}
        </div>
      </div>
    )
  }

  const statsQ = useQuery({
    queryKey: ['admin-stats'],
    queryFn: async () => (await adminAPI.stats()).data,
    enabled: tab === 'overview',
    retry: 1,
  })

  const usersQ = useQuery({
    queryKey: ['admin-utilisateurs', recherche, page],
    queryFn: async () => (await adminAPI.utilisateurs({ recherche: recherche || undefined, page, par_page: 50 })).data,
    enabled: tab === 'utilisateurs',
    retry: 1,
  })

  const detailsQ = useQuery({
    queryKey: ['admin-detail', userOuvert],
    queryFn: async () => userOuvert ? (await adminAPI.detailsUtilisateur(userOuvert)).data : null,
    enabled: !!userOuvert,
    retry: 1,
  })

  const ajouterCreditsM = useMutation({
    mutationFn: ({ user_id, credits, raison }: { user_id: number; credits: number; raison?: string }) =>
      adminAPI.ajouterCredits(user_id, credits, raison).then(r => r.data),
    onSuccess: (data: any) => {
      toast.success(data.message || t('admin.creditsAdded'))
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
      qc.invalidateQueries({ queryKey: ['admin-detail'] })
      qc.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('admin.errGeneric')),
  })

  const bloquerM = useMutation({
    mutationFn: ({ user_id, jours }: { user_id: number; jours: number }) =>
      adminAPI.bloquer(user_id, jours),
    onSuccess: () => {
      toast.success(t('admin.userBlocked'))
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
      qc.invalidateQueries({ queryKey: ['admin-detail'] })
    },
  })

  const debloquerM = useMutation({
    mutationFn: (user_id: number) => adminAPI.debloquer(user_id),
    onSuccess: () => {
      toast.success(t('admin.userUnblocked'))
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
      qc.invalidateQueries({ queryKey: ['admin-detail'] })
    },
  })

  return (
    <div className="space-y-5">
      <header className="flex items-center gap-3">
        <Shield className="text-amber-600" size={28} />
        <div>
          <h1 className="text-2xl font-bold">{t('admin.title')}</h1>
          <p className="text-sm text-gray-500">{t('admin.subtitle')}</p>
        </div>
      </header>

      {/* Tabs */}
      <nav className="flex gap-2 border-b overflow-x-auto">
        {([
          ['overview',     t('admin.tabOverview'),    LayoutDashboard],
          ['utilisateurs', t('admin.tabUsers'),       Users],
          ['revenus',      t('admin.tabRevenus'),     DollarSign],
          ['promotions',   t('admin.tabPromotions'),  Megaphone],
        ] as const).map(([key, label, Icon]) => (
          <button key={key} onClick={() => setTab(key as any)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition flex items-center gap-1.5 whitespace-nowrap ${
              tab === key ? 'border-amber-600 text-amber-700' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </nav>

      {/* Vue d'ensemble */}
      {tab === 'overview' && (
        <div className="space-y-4">
          {statsQ.isLoading && (
            <div className="text-center py-8 text-gray-500">
              <Loader2 className="inline animate-spin mr-2" size={16} /> {t('common.loading')}
            </div>
          )}
          {statsQ.data && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label={t('admin.kpiUsers')} value={fmtNb(statsQ.data.utilisateurs?.total ?? 0)}
                     sub={t('admin.kpiUsersSub', { actifs: statsQ.data.utilisateurs?.actifs ?? 0, nouveaux: statsQ.data.utilisateurs?.nouveaux_30j ?? 0 })} />
                <KPI label={t('admin.kpiCreditsRestants')}
                     value={fmtNb(statsQ.data.credits?.total_restants ?? 0)}
                     sub={`≈ ${fmtFcfa(statsQ.data.credits?.fcfa_equivalent ?? 0)}`} />
                <KPI label={t('admin.kpiConsom7j')}
                     value={fmtNb(statsQ.data.consommation_7j?.credits ?? 0)}
                     sub={t('admin.callsCount', { n: statsQ.data.consommation_7j?.appels ?? 0 })} />
                <KPI label={t('admin.kpiConsom30j')}
                     value={fmtNb(statsQ.data.consommation_30j?.credits ?? 0)}
                     sub={t('admin.callsCount', { n: statsQ.data.consommation_30j?.appels ?? 0 })} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-white rounded-xl border border-gray-200 p-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <TrendingUp size={14} className="text-amber-600" /> {t('admin.topModules30j')}
                  </h3>
                  {(statsQ.data.top_modules_30j || []).length === 0 ? (
                    <p className="text-sm text-gray-500">{t('admin.noConsumption')}</p>
                  ) : (
                    <div className="space-y-2">
                      {statsQ.data.top_modules_30j.map((m: any) => {
                        const max = statsQ.data.top_modules_30j[0]?.credits || 1
                        const pct = (m.credits / max) * 100
                        return (
                          <div key={m.module}>
                            <div className="flex items-center justify-between text-sm">
                              <span className="font-medium text-gray-700">{MODULE_LABEL_KEYS[m.module] ? t(MODULE_LABEL_KEYS[m.module]) : m.module}</span>
                              <span className="text-gray-500 text-xs">{t('admin.creditsCallsLine', { credits: fmtNb(m.credits), calls: fmtNb(m.appels) })}</span>
                            </div>
                            <div className="bg-gray-100 rounded-full h-2 mt-1 overflow-hidden">
                              <div className="bg-amber-500 h-full" style={{ width: `${Math.max(2, pct)}%` }} />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <Users size={14} className="text-amber-600" /> {t('admin.topUsers30j')}
                  </h3>
                  {(statsQ.data.top_utilisateurs_30j || []).length === 0 ? (
                    <p className="text-sm text-gray-500">{t('admin.noConsumption')}</p>
                  ) : (
                    <div className="space-y-2">
                      {statsQ.data.top_utilisateurs_30j.map((u: any) => (
                        <div key={u.user_id} className="flex items-center justify-between text-sm border-b border-gray-100 pb-2 last:border-0">
                          <div>
                            <div className="font-medium text-gray-900">{u.nom || u.email}</div>
                            <div className="text-xs text-gray-500">{u.email}</div>
                          </div>
                          <div className="text-right">
                            <div className="font-semibold text-amber-700">{fmtNb(u.credits)}</div>
                            <button onClick={() => { setTab('utilisateurs'); setUserOuvert(u.user_id) }}
                              className="text-[10px] text-amber-600 hover:text-amber-800">{t('admin.viewDetails')}</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Utilisateurs */}
      {tab === 'utilisateurs' && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1 max-w-md">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input value={recherche} onChange={e => { setRecherche(e.target.value); setPage(1) }}
                placeholder={t('admin.searchUsers')}
                className="w-full pl-9 pr-3 py-2 text-sm border rounded-lg" />
            </div>
            <span className="text-xs text-gray-500">
              {t('admin.usersCount', { n: usersQ.data?.total ?? 0 })}
            </span>
          </div>

          {usersQ.isLoading && (
            <div className="text-center py-8 text-gray-500">
              <Loader2 className="inline animate-spin mr-2" size={16} /> {t('common.loading')}
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="text-left px-3 py-2">{t('admin.user')}</th>
                    <th className="text-left px-3 py-2">{t('admin.role')}</th>
                    <th className="text-right px-3 py-2">{t('admin.creditsRestants')}</th>
                    <th className="text-right px-3 py-2">{t('admin.creditsConsumed')}</th>
                    <th className="text-left px-3 py-2">{t('admin.lastLogin')}</th>
                    <th className="text-left px-3 py-2">{t('common.status')}</th>
                    <th className="text-right px-3 py-2">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(usersQ.data?.utilisateurs || []).map((u: any) => (
                    <tr key={u.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2">
                        <div className="font-medium">{u.nom || u.username}</div>
                        <div className="text-xs text-gray-500">{u.email}</div>
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                          ADMIN_ROLES.includes(u.role) ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'
                        }`}>{u.role}</span>
                      </td>
                      <td className="px-3 py-2 text-right font-semibold">
                        {fmtNb(u.credits?.credits_restants ?? 0)}
                        <div className="text-[10px] text-gray-400">≈ {fmtFcfa(u.credits?.fcfa_equivalent ?? 0)}</div>
                      </td>
                      <td className="px-3 py-2 text-right text-gray-500">
                        {fmtNb(u.credits?.credits_utilises ?? 0)}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        {fmtDate(u.derniere_connexion, true)}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {u.actif
                          ? <span className="text-emerald-600">{t('admin.active')}</span>
                          : <span className="text-red-600">⏸ {u.bloque_jusqu_au ? t('admin.blockedShort') : t('admin.inactiveShort')}</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => setUserOuvert(u.id)}
                          className="text-xs px-2 py-1 rounded bg-amber-50 hover:bg-amber-100 text-amber-700">
                          <Eye size={11} className="inline mr-0.5" /> {t('common.details')}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {(usersQ.data?.utilisateurs || []).length === 0 && !usersQ.isLoading && (
                    <tr><td colSpan={7} className="text-center py-8 text-gray-500">{t('common.noResults')}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {usersQ.data && usersQ.data.total_pages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="px-3 py-1 rounded border disabled:opacity-50">‹ {t('common.previous')}</button>
              <span className="text-gray-500">{t('common.page')} {page} / {usersQ.data.total_pages}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={page >= usersQ.data.total_pages}
                className="px-3 py-1 rounded border disabled:opacity-50">{t('common.next')} ›</button>
            </div>
          )}
        </div>
      )}

      {/* Revenus */}
      {tab === 'revenus' && <RevenusTab />}

      {/* Promotions */}
      {tab === 'promotions' && <PromotionsTab />}

      {/* Modal détails utilisateur */}
      {userOuvert && (
        <UserDetailModal
          user_id={userOuvert}
          data={detailsQ.data}
          loading={detailsQ.isLoading}
          onClose={() => setUserOuvert(null)}
          onAjouterCredits={(c, r) => ajouterCreditsM.mutate({ user_id: userOuvert, credits: c, raison: r })}
          onBloquer={(j) => bloquerM.mutate({ user_id: userOuvert, jours: j })}
          onDebloquer={() => debloquerM.mutate(userOuvert)}
          busy={ajouterCreditsM.isPending || bloquerM.isPending || debloquerM.isPending}
        />
      )}
    </div>
  )
}

// ─── Composants ───────────────────────────────────────────────────────────────

function KPI({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-3">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-xl font-bold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-[10px] text-gray-400 mt-0.5">{sub}</div>}
    </div>
  )
}

function UserDetailModal({
  user_id, data, loading, onClose, onAjouterCredits, onBloquer, onDebloquer, busy,
}: {
  user_id: number; data: any; loading: boolean; onClose: () => void;
  onAjouterCredits: (credits: number, raison?: string) => void;
  onBloquer: (jours: number) => void;
  onDebloquer: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation()
  const [bonusCredits, setBonusCredits] = useState(1000)
  const [bonusRaison, setBonusRaison] = useState('')
  const [joursBlocage, setJoursBlocage] = useState(7)

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end md:items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-t-2xl md:rounded-2xl max-w-3xl w-full p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Users size={18} /> {t('admin.modUserTitle', { id: user_id })}
          </h3>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>

        {loading && (
          <div className="text-center py-8 text-gray-500">
            <Loader2 className="inline animate-spin mr-2" size={16} /> {t('admin.loadingInline')}
          </div>
        )}

        {data && (
          <>
            {/* Info user */}
            <div className="bg-gray-50 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              <Info label={t('common.name')} value={`${data.utilisateur.prenoms || ''} ${data.utilisateur.nom || ''}`.trim() || data.utilisateur.username} />
              <Info label={t('common.email')} value={data.utilisateur.email} />
              <Info label={t('admin.role')} value={data.utilisateur.role} />
              <Info label={t('common.phone')} value={data.utilisateur.telephone || '—'} />
              <Info label={t('admin.infoCreatedOn')} value={fmtDate(data.utilisateur.cree_le)} />
              <Info label={t('admin.lastLogin')} value={fmtDate(data.utilisateur.derniere_connexion, true)} />
              <Info label={t('admin.infoConnections')} value={fmtNb(data.utilisateur.nb_connexions)} />
              <Info label={t('common.status')} value={data.utilisateur.actif ? t('admin.active') : (data.utilisateur.bloque_jusqu_au ? t('admin.infoBlockedUntil', { date: fmtDate(data.utilisateur.bloque_jusqu_au, true) }) : t('admin.inactiveShort'))} />
            </div>

            {/* Solde crédits */}
            {data.credits && (
              <div className="bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-4 grid grid-cols-3 gap-3 text-center">
                <div>
                  <div className="text-xs text-amber-700 uppercase">{t('admin.creditsRestants')}</div>
                  <div className="text-2xl font-bold text-amber-900">{fmtNb(data.credits.credits_restants)}</div>
                  <div className="text-[10px] text-amber-700">≈ {fmtFcfa(Math.round((data.credits.credits_restants || 0) * 0.6))}</div>
                </div>
                <div>
                  <div className="text-xs text-amber-700 uppercase">{t('admin.creditsConsumed')}</div>
                  <div className="text-2xl font-bold text-amber-900">{fmtNb(data.credits.credits_utilises)}</div>
                </div>
                <div>
                  <div className="text-xs text-amber-700 uppercase">{t('admin.creditsAlloues')}</div>
                  <div className="text-2xl font-bold text-amber-900">{fmtNb(data.credits.credits_alloues)}</div>
                </div>
              </div>
            )}

            {/* Octroi crédits */}
            <div className="bg-white border border-amber-200 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-amber-900 flex items-center gap-2">
                <Wallet size={14} /> {t('admin.grantBonus')}
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">{t('admin.grantCredits')}</label>
                  <input type="number" min={1} step={500} value={bonusCredits}
                    onChange={e => setBonusCredits(Math.max(1, parseInt(e.target.value) || 0))}
                    className="w-full border rounded-lg px-3 py-2 text-sm" />
                </div>
                <div className="sm:col-span-2">
                  <label className="text-xs text-gray-500 block mb-1">{t('admin.grantReason')}</label>
                  <input value={bonusRaison} onChange={e => setBonusRaison(e.target.value)}
                    placeholder={t('admin.grantReasonPh')}
                    className="w-full border rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                {[500, 1000, 5000, 10000].map(n => (
                  <button key={n} onClick={() => setBonusCredits(n)}
                    className="text-xs px-2 py-1 rounded bg-amber-100 hover:bg-amber-200 text-amber-700">
                    {fmtNb(n)}
                  </button>
                ))}
                <div className="flex-1" />
                <button onClick={() => onAjouterCredits(bonusCredits, bonusRaison || undefined)} disabled={busy}
                  className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg flex items-center gap-1.5">
                  <Plus size={14} /> {t('admin.grantBtn', { n: fmtNb(bonusCredits) })}
                </button>
              </div>
            </div>

            {/* Bloquer / Débloquer */}
            <div className="bg-white border border-red-200 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-red-700 flex items-center gap-2">
                <Lock size={14} /> {t('admin.moderation')}
              </h4>
              {data.utilisateur.bloque_jusqu_au ? (
                <button onClick={onDebloquer} disabled={busy}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold px-4 py-2 rounded-lg flex items-center gap-1.5">
                  <Unlock size={14} /> {t('admin.unblockUser')}
                </button>
              ) : (
                <div className="flex items-center gap-2 flex-wrap">
                  <input type="number" min={1} max={365} value={joursBlocage}
                    onChange={e => setJoursBlocage(Math.max(1, parseInt(e.target.value) || 1))}
                    className="w-20 border rounded-lg px-2 py-1 text-sm" />
                  <span className="text-xs text-gray-500">{t('admin.blockDays')}</span>
                  <button onClick={() => onBloquer(joursBlocage)} disabled={busy}
                    className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg flex items-center gap-1.5">
                    <Lock size={14} /> {t('admin.blockUser')}
                  </button>
                </div>
              )}
            </div>

            {/* Top modules */}
            {(data.top_modules_30j || []).length > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <h4 className="font-semibold text-gray-700 mb-2 text-sm">{t('admin.topModulesUser')}</h4>
                <div className="space-y-1.5">
                  {data.top_modules_30j.map((m: any) => (
                    <div key={m.module} className="flex items-center justify-between text-xs">
                      <span>{MODULE_LABEL_KEYS[m.module] ? t(MODULE_LABEL_KEYS[m.module]) : m.module}</span>
                      <span className="font-medium">{t('admin.creditsCallsLine', { credits: fmtNb(m.credits), calls: fmtNb(m.appels) })}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Dernières consos */}
            {(data.dernieres_consommations || []).length > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <h4 className="font-semibold text-gray-700 p-3 border-b text-sm">{t('admin.lastConsumption')}</h4>
                <div className="overflow-x-auto max-h-64">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 uppercase sticky top-0">
                      <tr>
                        <th className="text-left px-2 py-1.5">{t('admin.consumDate')}</th>
                        <th className="text-left px-2 py-1.5">{t('admin.consumModule')}</th>
                        <th className="text-left px-2 py-1.5">{t('admin.consumModel')}</th>
                        <th className="text-right px-2 py-1.5">{t('admin.consumCredits')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {data.dernieres_consommations.map((co: any) => (
                        <tr key={co.id}>
                          <td className="px-2 py-1.5 text-gray-500">{fmtDate(co.date, true)}</td>
                          <td className="px-2 py-1.5">{MODULE_LABEL_KEYS[co.module] ? t(MODULE_LABEL_KEYS[co.module]) : co.module}</td>
                          <td className="px-2 py-1.5 text-gray-500">
                            {(co.modele || '').startsWith('forfait:') ? t('abonnement.forfaitPrefix', { name: (co.modele || '').replace('forfait:', '') }) : co.modele}
                          </td>
                          <td className="px-2 py-1.5 text-right font-semibold text-amber-700">{fmtNb(co.credits_debites)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Info({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-sm font-medium text-gray-900">{value}</div>
    </div>
  )
}

function PromotionsTab() {
  const { t } = useTranslation()
  const [montant, setMontant] = useState(1000)
  const [cible, setCible] = useState<'tous' | 'ids' | 'consommation' | 'role'>('tous')
  const [role, setRole] = useState('agent')
  const [userIdsRaw, setUserIdsRaw] = useState('')
  const [motif, setMotif] = useState('')
  const [seuilCreditsMin, setSeuilCreditsMin] = useState('')
  const [seuilCreditsMax, setSeuilCreditsMax] = useState('')
  const [seuilAppelsMin, setSeuilAppelsMin] = useState('')
  const [periodeJours, setPeriodeJours] = useState(30)
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (montant <= 0) { toast.error(t('admin.errAmountInvalid')); return }
    let user_ids: number[] | undefined
    if (cible === 'ids') {
      user_ids = userIdsRaw.split(/[\s,]+/).map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n > 0)
      if (!user_ids.length) { toast.error(t('admin.errIdsList')); return }
    }
    if (cible === 'consommation' && !seuilCreditsMin && !seuilCreditsMax && !seuilAppelsMin) {
      toast.error(t('admin.errThresholdRequired')); return
    }
    const targetLabel = cible === 'tous' ? t('admin.targetLabelTous')
      : cible === 'ids' ? t('admin.targetLabelIds')
      : cible === 'consommation' ? t('admin.targetLabelConsommation')
      : t('admin.targetLabelRole')
    if (!confirm(t('admin.confirmDistribute', { credits: fmtNb(montant), target: targetLabel }))) return

    setBusy(true)
    try {
      const r = await adminAPI.lancerPromotion({
        montant, cible,
        user_ids,
        role: cible === 'role' ? role : undefined,
        seuil_credits_min: cible === 'consommation' && seuilCreditsMin ? parseFloat(seuilCreditsMin) : undefined,
        seuil_credits_max: cible === 'consommation' && seuilCreditsMax ? parseFloat(seuilCreditsMax) : undefined,
        seuil_appels_min:  cible === 'consommation' && seuilAppelsMin  ? parseInt(seuilAppelsMin) : undefined,
        periode_jours: cible === 'consommation' ? periodeJours : undefined,
        motif: motif || undefined,
      })
      const data = (r as any).data || r
      toast.success(data.message || t('admin.distributedToBeneficiaries', { n: data.beneficiaires }))
      setMontant(1000); setUserIdsRaw(''); setMotif('')
      setSeuilCreditsMin(''); setSeuilCreditsMax(''); setSeuilAppelsMin('')
      qc.invalidateQueries({ queryKey: ['admin-stats'] })
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || t('admin.errDistribution'))
    } finally { setBusy(false) }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 max-w-3xl">
      <div className="flex items-center gap-2 mb-3">
        <Megaphone size={18} className="text-amber-600" />
        <h3 className="text-lg font-bold text-gray-900">{t('admin.promotionTitle')}</h3>
      </div>
      <p className="text-sm text-gray-500 mb-5">
        {t('admin.promotionDesc')}
      </p>

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700 block mb-1">{t('admin.promotionAmount')}</label>
          <input type="number" min={1} value={montant} onChange={e => setMontant(parseInt(e.target.value) || 0)}
            className="w-full border rounded-lg px-3 py-2 text-sm" />
          <p className="text-xs text-gray-400 mt-1">{t('admin.fcfaPerBeneficiary', { amount: fmtFcfa(Math.round(montant * 0.6)) })}</p>
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 block mb-2">{t('admin.promotionTarget')}</label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { v: 'tous',        lbl: t('admin.promotionTargetAll'),    d: t('admin.targetTousDesc') },
              { v: 'role',        lbl: t('admin.promotionTargetRole'),   d: t('admin.targetRoleDesc') },
              { v: 'ids',         lbl: t('admin.promotionTargetIds'),    d: t('admin.targetIdsDesc') },
              { v: 'consommation',lbl: t('admin.promotionTargetConsom'), d: t('admin.targetConsomDesc') },
            ].map(c => (
              <button key={c.v} type="button" onClick={() => setCible(c.v as any)}
                className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                  cible === c.v ? 'border-amber-500 bg-amber-50' : 'border-gray-200 hover:border-gray-300'
                }`}>
                <div className="font-semibold">{c.lbl}</div>
                <div className="text-xs text-gray-500">{c.d}</div>
              </button>
            ))}
          </div>
        </div>

        {cible === 'role' && (
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">{t('admin.targetRoleLabel')}</label>
            <select value={role} onChange={e => setRole(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm">
              <option value="agent">agent</option>
              <option value="manager">manager</option>
              <option value="admin">admin</option>
              <option value="super_admin">super_admin</option>
            </select>
          </div>
        )}

        {cible === 'ids' && (
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">{t('admin.userIdsLabel')}</label>
            <textarea value={userIdsRaw} onChange={e => setUserIdsRaw(e.target.value)} rows={3}
              placeholder={t('admin.userIdsPlaceholder')}
              className="w-full border rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        )}

        {cible === 'consommation' && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-3">
            <div className="text-sm font-medium text-gray-700">{t('admin.thresholdsTitle')}</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label={t('admin.thresholdCreditsMin')}>
                <input type="number" min={0} value={seuilCreditsMin} onChange={e => setSeuilCreditsMin(e.target.value)}
                  placeholder={t('admin.thresholdMinPlaceholder')}
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
              <Field label={t('admin.thresholdCreditsMax')}>
                <input type="number" min={0} value={seuilCreditsMax} onChange={e => setSeuilCreditsMax(e.target.value)}
                  placeholder={t('admin.thresholdMaxPlaceholder')}
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
              <Field label={t('admin.thresholdCallsMin')}>
                <input type="number" min={0} value={seuilAppelsMin} onChange={e => setSeuilAppelsMin(e.target.value)}
                  placeholder={t('admin.thresholdCallsPlaceholder')}
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
              <Field label={t('admin.thresholdPeriod')}>
                <input type="number" min={1} max={365} value={periodeJours}
                  onChange={e => setPeriodeJours(Math.max(1, parseInt(e.target.value) || 30))}
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
            </div>
          </div>
        )}

        <div>
          <label className="text-sm font-medium text-gray-700 block mb-1">{t('admin.promotionMotif')}</label>
          <input value={motif} onChange={e => setMotif(e.target.value)}
            placeholder={t('admin.motifPlaceholder')}
            className="w-full border rounded-lg px-3 py-2 text-sm" />
        </div>

        <button type="submit" disabled={busy}
          className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Megaphone size={14} />}
          {busy ? t('admin.promotionLaunching') : t('admin.promotionLaunch')}
        </button>
      </form>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-gray-500 block mb-1">{label}</label>
      {children}
    </div>
  )
}

// ─── Revenus CA ────────────────────────────────────────────────────────────────

type RangePreset = 'all' | '7j' | '30j' | '90j' | 'mois' | 'annee' | 'custom'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function isoMinusDays(jours: number): string {
  const d = new Date()
  d.setDate(d.getDate() - jours)
  return d.toISOString().slice(0, 10)
}

function debutMoisISO(): string {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}

function debutAnneeISO(): string {
  const d = new Date()
  return new Date(d.getFullYear(), 0, 1).toISOString().slice(0, 10)
}

function variationPct(actuel: number, precedent: number): number | null {
  if (!precedent) return actuel > 0 ? 100 : null
  return ((actuel - precedent) / precedent) * 100
}

function VariationBadge({ actuel, precedent }: { actuel: number; precedent: number }) {
  const v = variationPct(actuel, precedent)
  if (v === null) return null
  const positif = v >= 0
  const Icon = positif ? ArrowUpRight : ArrowDownRight
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium ${
      positif ? 'text-emerald-600' : 'text-red-600'
    }`}>
      <Icon size={10} /> {Math.abs(v).toFixed(1)}%
    </span>
  )
}

function RevenusTab() {
  const { t } = useTranslation()
  const [preset, setPreset] = useState<RangePreset>('30j')
  const [dateDebut, setDateDebut] = useState<string>(isoMinusDays(30))
  const [dateFin, setDateFin]     = useState<string>(todayISO())

  const appliquerPreset = (p: RangePreset) => {
    setPreset(p)
    if (p === 'all') { setDateDebut(''); setDateFin('') }
    else if (p === '7j')   { setDateDebut(isoMinusDays(7));   setDateFin(todayISO()) }
    else if (p === '30j')  { setDateDebut(isoMinusDays(30));  setDateFin(todayISO()) }
    else if (p === '90j')  { setDateDebut(isoMinusDays(90));  setDateFin(todayISO()) }
    else if (p === 'mois') { setDateDebut(debutMoisISO());    setDateFin(todayISO()) }
    else if (p === 'annee'){ setDateDebut(debutAnneeISO());   setDateFin(todayISO()) }
  }

  const params = preset === 'all'
    ? undefined
    : { date_debut: dateDebut || undefined, date_fin: dateFin || undefined }

  const revenusQ = useQuery({
    queryKey: ['admin-revenus', preset, dateDebut, dateFin],
    queryFn: async () => (await adminAPI.statsRevenus(params)).data,
    retry: 1,
  })

  if (revenusQ.isLoading) {
    return (
      <div className="text-center py-12 text-gray-500">
        <Loader2 className="inline animate-spin mr-2" size={16} /> {t('admin.loadingRevenus')}
      </div>
    )
  }
  if (revenusQ.isError) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
        <AlertCircle className="inline mr-2" size={14} /> {t('admin.errLoadRevenus')}
      </div>
    )
  }

  const d = revenusQ.data
  if (!d) return null

  const periodeActive = !!(dateDebut || dateFin)
  const evolutionMax = Math.max(1, ...(d.evolution_12mois || []).map((m: any) => m.montant || 0))

  return (
    <div className="space-y-4">
      {/* Présets de période */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 flex flex-wrap items-center gap-2">
        <Calendar size={14} className="text-gray-400" />
        <span className="text-xs text-gray-500 mr-1">{t('admin.revenusFilters')}</span>
        {([
          ['7j',    t('admin.preset7d')],
          ['30j',   t('admin.preset30d')],
          ['90j',   t('admin.preset90d')],
          ['mois',  t('admin.presetMonth')],
          ['annee', t('admin.presetYear')],
          ['all',   t('admin.presetAll')],
        ] as const).map(([k, lbl]) => (
          <button key={k} onClick={() => appliquerPreset(k as RangePreset)}
            className={`text-xs px-2.5 py-1 rounded-full border transition ${
              preset === k ? 'bg-amber-600 text-white border-amber-600' : 'bg-white text-gray-600 hover:bg-gray-50 border-gray-200'
            }`}>{lbl}</button>
        ))}
        <div className="flex items-center gap-1 ml-2">
          <input type="date" value={dateDebut} onChange={e => { setDateDebut(e.target.value); setPreset('custom') }}
            className="text-xs border rounded px-2 py-1" />
          <span className="text-xs text-gray-400">→</span>
          <input type="date" value={dateFin} onChange={e => { setDateFin(e.target.value); setPreset('custom') }}
            className="text-xs border rounded px-2 py-1" />
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 border border-emerald-200 rounded-xl p-4">
          <div className="text-xs text-emerald-700 uppercase tracking-wide flex items-center gap-1">
            <DollarSign size={11} /> {t('admin.kpiCaTotal')}
          </div>
          <div className="text-2xl font-bold text-emerald-900 mt-1">{fmtFcfa(d.ca_total_fcfa)}</div>
          <div className="text-[10px] text-emerald-700 mt-0.5">
            {t('admin.rechargesAndClients', { recharges: fmtNb(d.nb_transactions_total), clients: fmtNb(d.nb_clients_payants) })}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-xs text-gray-500 uppercase">{t('admin.kpiCaToday')}</div>
          <div className="text-2xl font-bold text-gray-900 mt-1">{fmtFcfa(d.ca_aujourdhui?.montant)}</div>
          <div className="flex items-center gap-2 text-[10px] text-gray-400 mt-0.5">
            <span>{t('admin.txCount', { n: fmtNb(d.ca_aujourdhui?.transactions ?? 0) })}</span>
            <VariationBadge actuel={d.ca_aujourdhui?.montant ?? 0} precedent={d.ca_aujourdhui_precedent?.montant ?? 0} />
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-xs text-gray-500 uppercase">{t('admin.kpiCa7j')}</div>
          <div className="text-2xl font-bold text-gray-900 mt-1">{fmtFcfa(d.ca_7j?.montant)}</div>
          <div className="flex items-center gap-2 text-[10px] text-gray-400 mt-0.5">
            <span>{t('admin.txCount', { n: fmtNb(d.ca_7j?.transactions ?? 0) })}</span>
            <VariationBadge actuel={d.ca_7j?.montant ?? 0} precedent={d.ca_7j_precedent?.montant ?? 0} />
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="text-xs text-gray-500 uppercase">{t('admin.kpiCa30j')}</div>
          <div className="text-2xl font-bold text-gray-900 mt-1">{fmtFcfa(d.ca_30j?.montant)}</div>
          <div className="flex items-center gap-2 text-[10px] text-gray-400 mt-0.5">
            <span>{t('admin.txCount', { n: fmtNb(d.ca_30j?.transactions ?? 0) })}</span>
            <VariationBadge actuel={d.ca_30j?.montant ?? 0} precedent={d.ca_30j_precedent?.montant ?? 0} />
          </div>
        </div>
      </div>

      {/* Bandeau période personnalisée */}
      {periodeActive && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs text-amber-700 uppercase">{t('admin.periodTitle')}</div>
            <div className="text-2xl font-bold text-amber-900">{fmtFcfa(d.ca_periode?.montant)}</div>
            <div className="text-[10px] text-amber-700">
              {t('admin.rechargesAndClients', { recharges: fmtNb(d.ca_periode?.transactions ?? 0), clients: fmtNb(d.ca_periode?.clients ?? 0) })}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-amber-700 uppercase">{t('admin.vsPeriodPrec')}</div>
            <div className="text-sm font-semibold text-amber-900">{fmtFcfa(d.ca_periode_precedente?.montant)}</div>
            <VariationBadge actuel={d.ca_periode?.montant ?? 0} precedent={d.ca_periode_precedente?.montant ?? 0} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Évolution mensuelle */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <BarChart3 size={14} className="text-amber-600" /> {t('admin.evolutionMonthly')}
          </h3>
          {(d.evolution_12mois || []).length === 0 ? (
            <p className="text-sm text-gray-500">{t('admin.noRechargesPeriod')}</p>
          ) : (
            <div className="space-y-2">
              {d.evolution_12mois.map((m: any) => {
                const pct = ((m.montant || 0) / evolutionMax) * 100
                return (
                  <div key={m.mois}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-gray-600">{m.mois}</span>
                      <span className="text-gray-500">{t('admin.monthAxis', { amount: fmtFcfa(m.montant), tx: fmtNb(m.transactions) })}</span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2 mt-1 overflow-hidden">
                      <div className="bg-emerald-500 h-full" style={{ width: `${Math.max(2, pct)}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Top packs */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <TrendingUp size={14} className="text-amber-600" /> {t('admin.topPacks')}
          </h3>
          {(d.par_pack || []).length === 0 ? (
            <p className="text-sm text-gray-500">{t('common.noData')}.</p>
          ) : (
            <div className="space-y-2">
              {d.par_pack.slice(0, 8).map((p: any) => {
                const max = d.par_pack[0]?.montant || 1
                const pct = ((p.montant || 0) / max) * 100
                return (
                  <div key={p.pack}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-gray-700 truncate pr-2">{p.pack}</span>
                      <span className="text-gray-500 whitespace-nowrap">
                        {t('admin.packLine', { amount: fmtFcfa(p.montant), tx: fmtNb(p.transactions), credits: fmtNb(p.credits) })}
                      </span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2 mt-1 overflow-hidden">
                      <div className="bg-amber-500 h-full" style={{ width: `${Math.max(2, pct)}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Dernières transactions */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <h3 className="text-sm font-semibold text-gray-700 p-4 border-b flex items-center gap-2">
          <Wallet size={14} className="text-amber-600" /> {t('admin.lastRecharges')}
        </h3>
        {(d.dernieres_transactions || []).length === 0 ? (
          <p className="text-sm text-gray-500 p-6 text-center">{t('admin.noRecharges')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-500 uppercase">
                <tr>
                  <th className="text-left px-3 py-2">{t('common.date')}</th>
                  <th className="text-left px-3 py-2">{t('admin.user')}</th>
                  <th className="text-left px-3 py-2">{t('admin.headerPack')}</th>
                  <th className="text-right px-3 py-2">{t('common.credits')}</th>
                  <th className="text-right px-3 py-2">{t('common.amount')}</th>
                  <th className="text-left px-3 py-2">{t('abonnement.reference')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {d.dernieres_transactions.map((t: any) => (
                  <tr key={t.reference || `${t.user_id}-${t.date}`} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{fmtDate(t.date, true)}</td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-gray-900">{t.nom || t.email || `#${t.user_id}`}</div>
                      {t.email && <div className="text-[10px] text-gray-500">{t.email}</div>}
                    </td>
                    <td className="px-3 py-2 text-gray-600">{t.pack_nom}</td>
                    <td className="px-3 py-2 text-right font-medium text-amber-700">{fmtNb(t.credits)}</td>
                    <td className="px-3 py-2 text-right font-semibold text-emerald-700">{fmtFcfa(t.montant)}</td>
                    <td className="px-3 py-2 text-gray-400 font-mono text-[10px]">{t.reference}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
