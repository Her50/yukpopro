import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Shield, Users, Search, X, Loader2, Plus, Lock, Unlock, TrendingUp,
  Wallet, BarChart3, Eye, AlertCircle, Megaphone, LayoutDashboard,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { adminAPI } from '../api/client'
import { useAuth } from '../context/AuthContext'

const ADMIN_ROLES = ['admin', 'super_admin', 'yukpo_owner']

const MODULE_LABELS: Record<string, string> = {
  redaction:    'Rédaction Yukpo',
  ocr:          'Scan / OCR',
  audio:        'Audio Yukpo',
  traduction:   'Traduction Yukpo',
  infographie:  'Infographie',
  designerpro:  'Designer Pro',
  gestion:      'Gestion',
  documents:    'Mes Documents',
  bureau:       'Yukpo Secrétariat',
  inconnu:      'Autre',
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
  const { user } = useAuth()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'overview' | 'utilisateurs' | 'promotions'>('overview')
  const [recherche, setRecherche] = useState('')
  const [page, setPage] = useState(1)
  const [userOuvert, setUserOuvert] = useState<number | null>(null)

  // Garde rôle
  if (user && !ADMIN_ROLES.includes(user.role)) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          <AlertCircle className="inline mr-2" size={14} />
          Accès réservé aux administrateurs Yukpo. Votre rôle : <strong>{user.role}</strong>.
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
      toast.success(data.message || 'Crédits ajoutés')
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
      qc.invalidateQueries({ queryKey: ['admin-detail'] })
      qc.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Erreur'),
  })

  const bloquerM = useMutation({
    mutationFn: ({ user_id, jours }: { user_id: number; jours: number }) =>
      adminAPI.bloquer(user_id, jours),
    onSuccess: () => {
      toast.success('Utilisateur bloqué')
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
      qc.invalidateQueries({ queryKey: ['admin-detail'] })
    },
  })

  const debloquerM = useMutation({
    mutationFn: (user_id: number) => adminAPI.debloquer(user_id),
    onSuccess: () => {
      toast.success('Utilisateur débloqué')
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
      qc.invalidateQueries({ queryKey: ['admin-detail'] })
    },
  })

  return (
    <div className="space-y-5">
      <header className="flex items-center gap-3">
        <Shield className="text-amber-600" size={28} />
        <div>
          <h1 className="text-2xl font-bold">Administration Yukpo Secrétariat</h1>
          <p className="text-sm text-gray-500">Suivi des utilisateurs, octroi de crédits, statistiques</p>
        </div>
      </header>

      {/* Tabs */}
      <nav className="flex gap-2 border-b overflow-x-auto">
        {([
          ['overview',     "Vue d'ensemble", LayoutDashboard],
          ['utilisateurs', 'Utilisateurs',   Users],
          ['promotions',   'Promotions',     Megaphone],
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
              <Loader2 className="inline animate-spin mr-2" size={16} /> Chargement…
            </div>
          )}
          {statsQ.data && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="Utilisateurs" value={fmtNb(statsQ.data.utilisateurs?.total ?? 0)}
                     sub={`${statsQ.data.utilisateurs?.actifs ?? 0} actifs · ${statsQ.data.utilisateurs?.nouveaux_30j ?? 0} nouveaux 30j`} />
                <KPI label="Crédits restants (tous users)"
                     value={fmtNb(statsQ.data.credits?.total_restants ?? 0)}
                     sub={`≈ ${fmtFcfa(statsQ.data.credits?.fcfa_equivalent ?? 0)}`} />
                <KPI label="Consommation 7j"
                     value={fmtNb(statsQ.data.consommation_7j?.credits ?? 0)}
                     sub={`${statsQ.data.consommation_7j?.appels ?? 0} appel(s)`} />
                <KPI label="Consommation 30j"
                     value={fmtNb(statsQ.data.consommation_30j?.credits ?? 0)}
                     sub={`${statsQ.data.consommation_30j?.appels ?? 0} appel(s)`} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-white rounded-xl border border-gray-200 p-5">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <TrendingUp size={14} className="text-amber-600" /> Top modules consommateurs (30j)
                  </h3>
                  {(statsQ.data.top_modules_30j || []).length === 0 ? (
                    <p className="text-sm text-gray-500">Aucune consommation.</p>
                  ) : (
                    <div className="space-y-2">
                      {statsQ.data.top_modules_30j.map((m: any) => {
                        const max = statsQ.data.top_modules_30j[0]?.credits || 1
                        const pct = (m.credits / max) * 100
                        return (
                          <div key={m.module}>
                            <div className="flex items-center justify-between text-sm">
                              <span className="font-medium text-gray-700">{MODULE_LABELS[m.module] || m.module}</span>
                              <span className="text-gray-500 text-xs">{fmtNb(m.credits)} crédits · {fmtNb(m.appels)} appels</span>
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
                    <Users size={14} className="text-amber-600" /> Top utilisateurs (30j)
                  </h3>
                  {(statsQ.data.top_utilisateurs_30j || []).length === 0 ? (
                    <p className="text-sm text-gray-500">Aucune consommation.</p>
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
                              className="text-[10px] text-amber-600 hover:text-amber-800">Voir détails →</button>
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
                placeholder="Rechercher email / nom / username…"
                className="w-full pl-9 pr-3 py-2 text-sm border rounded-lg" />
            </div>
            <span className="text-xs text-gray-500">
              {usersQ.data?.total ?? 0} utilisateur(s)
            </span>
          </div>

          {usersQ.isLoading && (
            <div className="text-center py-8 text-gray-500">
              <Loader2 className="inline animate-spin mr-2" size={16} /> Chargement…
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="text-left px-3 py-2">Utilisateur</th>
                    <th className="text-left px-3 py-2">Rôle</th>
                    <th className="text-right px-3 py-2">Crédits restants</th>
                    <th className="text-right px-3 py-2">Consommés</th>
                    <th className="text-left px-3 py-2">Dernière connexion</th>
                    <th className="text-left px-3 py-2">Statut</th>
                    <th className="text-right px-3 py-2">Actions</th>
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
                          ? <span className="text-emerald-600">✓ Actif</span>
                          : <span className="text-red-600">⏸ {u.bloque_jusqu_au ? 'Bloqué' : 'Inactif'}</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => setUserOuvert(u.id)}
                          className="text-xs px-2 py-1 rounded bg-amber-50 hover:bg-amber-100 text-amber-700">
                          <Eye size={11} className="inline mr-0.5" /> Détails
                        </button>
                      </td>
                    </tr>
                  ))}
                  {(usersQ.data?.utilisateurs || []).length === 0 && !usersQ.isLoading && (
                    <tr><td colSpan={7} className="text-center py-8 text-gray-500">Aucun utilisateur</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {usersQ.data && usersQ.data.total_pages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="px-3 py-1 rounded border disabled:opacity-50">‹ Précédent</button>
              <span className="text-gray-500">Page {page} / {usersQ.data.total_pages}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={page >= usersQ.data.total_pages}
                className="px-3 py-1 rounded border disabled:opacity-50">Suivant ›</button>
            </div>
          )}
        </div>
      )}

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
  const [bonusCredits, setBonusCredits] = useState(1000)
  const [bonusRaison, setBonusRaison] = useState('')
  const [joursBlocage, setJoursBlocage] = useState(7)

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end md:items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-t-2xl md:rounded-2xl max-w-3xl w-full p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Users size={18} /> Utilisateur #{user_id}
          </h3>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>

        {loading && (
          <div className="text-center py-8 text-gray-500">
            <Loader2 className="inline animate-spin mr-2" size={16} /> Chargement…
          </div>
        )}

        {data && (
          <>
            {/* Info user */}
            <div className="bg-gray-50 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              <Info label="Nom" value={`${data.utilisateur.prenoms || ''} ${data.utilisateur.nom || ''}`.trim() || data.utilisateur.username} />
              <Info label="Email" value={data.utilisateur.email} />
              <Info label="Rôle" value={data.utilisateur.role} />
              <Info label="Téléphone" value={data.utilisateur.telephone || '—'} />
              <Info label="Créé le" value={fmtDate(data.utilisateur.cree_le)} />
              <Info label="Dernière connexion" value={fmtDate(data.utilisateur.derniere_connexion, true)} />
              <Info label="Connexions" value={fmtNb(data.utilisateur.nb_connexions)} />
              <Info label="Statut" value={data.utilisateur.actif ? '✓ Actif' : (data.utilisateur.bloque_jusqu_au ? `Bloqué jusqu'au ${fmtDate(data.utilisateur.bloque_jusqu_au, true)}` : 'Inactif')} />
            </div>

            {/* Solde crédits */}
            {data.credits && (
              <div className="bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-4 grid grid-cols-3 gap-3 text-center">
                <div>
                  <div className="text-xs text-amber-700 uppercase">Restants</div>
                  <div className="text-2xl font-bold text-amber-900">{fmtNb(data.credits.credits_restants)}</div>
                  <div className="text-[10px] text-amber-700">≈ {fmtFcfa(Math.round((data.credits.credits_restants || 0) * 0.6))}</div>
                </div>
                <div>
                  <div className="text-xs text-amber-700 uppercase">Consommés</div>
                  <div className="text-2xl font-bold text-amber-900">{fmtNb(data.credits.credits_utilises)}</div>
                </div>
                <div>
                  <div className="text-xs text-amber-700 uppercase">Total alloués</div>
                  <div className="text-2xl font-bold text-amber-900">{fmtNb(data.credits.credits_alloues)}</div>
                </div>
              </div>
            )}

            {/* Octroi crédits */}
            <div className="bg-white border border-amber-200 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-amber-900 flex items-center gap-2">
                <Wallet size={14} /> Octroyer des crédits bonus
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div>
                  <label className="text-xs text-gray-500 block mb-1">Crédits</label>
                  <input type="number" min={1} step={500} value={bonusCredits}
                    onChange={e => setBonusCredits(Math.max(1, parseInt(e.target.value) || 0))}
                    className="w-full border rounded-lg px-3 py-2 text-sm" />
                </div>
                <div className="sm:col-span-2">
                  <label className="text-xs text-gray-500 block mb-1">Raison (audit interne, optionnel)</label>
                  <input value={bonusRaison} onChange={e => setBonusRaison(e.target.value)}
                    placeholder="Ex: compensation panne, promo lancement…"
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
                  <Plus size={14} /> Ajouter {fmtNb(bonusCredits)} crédits
                </button>
              </div>
            </div>

            {/* Bloquer / Débloquer */}
            <div className="bg-white border border-red-200 rounded-xl p-4 space-y-3">
              <h4 className="font-semibold text-red-700 flex items-center gap-2">
                <Lock size={14} /> Modération
              </h4>
              {data.utilisateur.bloque_jusqu_au ? (
                <button onClick={onDebloquer} disabled={busy}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold px-4 py-2 rounded-lg flex items-center gap-1.5">
                  <Unlock size={14} /> Débloquer
                </button>
              ) : (
                <div className="flex items-center gap-2 flex-wrap">
                  <input type="number" min={1} max={365} value={joursBlocage}
                    onChange={e => setJoursBlocage(Math.max(1, parseInt(e.target.value) || 1))}
                    className="w-20 border rounded-lg px-2 py-1 text-sm" />
                  <span className="text-xs text-gray-500">jours</span>
                  <button onClick={() => onBloquer(joursBlocage)} disabled={busy}
                    className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg flex items-center gap-1.5">
                    <Lock size={14} /> Bloquer
                  </button>
                </div>
              )}
            </div>

            {/* Top modules */}
            {(data.top_modules_30j || []).length > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <h4 className="font-semibold text-gray-700 mb-2 text-sm">Modules les plus utilisés (30j)</h4>
                <div className="space-y-1.5">
                  {data.top_modules_30j.map((m: any) => (
                    <div key={m.module} className="flex items-center justify-between text-xs">
                      <span>{MODULE_LABELS[m.module] || m.module}</span>
                      <span className="font-medium">{fmtNb(m.credits)} crédits · {fmtNb(m.appels)} appels</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Dernières consos */}
            {(data.dernieres_consommations || []).length > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <h4 className="font-semibold text-gray-700 p-3 border-b text-sm">Dernières consommations (50)</h4>
                <div className="overflow-x-auto max-h-64">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 uppercase sticky top-0">
                      <tr>
                        <th className="text-left px-2 py-1.5">Date</th>
                        <th className="text-left px-2 py-1.5">Module</th>
                        <th className="text-left px-2 py-1.5">Modèle</th>
                        <th className="text-right px-2 py-1.5">Crédits</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {data.dernieres_consommations.map((co: any) => (
                        <tr key={co.id}>
                          <td className="px-2 py-1.5 text-gray-500">{fmtDate(co.date, true)}</td>
                          <td className="px-2 py-1.5">{MODULE_LABELS[co.module] || co.module}</td>
                          <td className="px-2 py-1.5 text-gray-500">
                            {(co.modele || '').startsWith('forfait:') ? (co.modele || '').replace('forfait:', 'Forfait ') : co.modele}
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
    if (montant <= 0) { toast.error('Montant invalide'); return }
    let user_ids: number[] | undefined
    if (cible === 'ids') {
      user_ids = userIdsRaw.split(/[\s,]+/).map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n > 0)
      if (!user_ids.length) { toast.error('Liste IDs invalide'); return }
    }
    if (cible === 'consommation' && !seuilCreditsMin && !seuilCreditsMax && !seuilAppelsMin) {
      toast.error("Au moins un seuil requis pour cible 'consommation'"); return
    }
    if (!confirm(`Distribuer ${fmtNb(montant)} crédits Yukpo à la cible "${cible}" ?`)) return

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
      toast.success(data.message || `Distribué à ${data.beneficiaires} utilisateur(s)`)
      setMontant(1000); setUserIdsRaw(''); setMotif('')
      setSeuilCreditsMin(''); setSeuilCreditsMax(''); setSeuilAppelsMin('')
      qc.invalidateQueries({ queryKey: ['admin-stats'] })
      qc.invalidateQueries({ queryKey: ['admin-utilisateurs'] })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Erreur distribution')
    } finally { setBusy(false) }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 max-w-3xl">
      <div className="flex items-center gap-2 mb-3">
        <Megaphone size={18} className="text-amber-600" />
        <h3 className="text-lg font-bold text-gray-900">Lancer une campagne</h3>
      </div>
      <p className="text-sm text-gray-500 mb-5">
        Distribue des crédits Yukpo bonus à un groupe d'utilisateurs (ajouté à <code className="text-amber-700">credits_alloues</code>).
        Idéal pour lancement, compensation panne, fidélisation des gros consommateurs, etc.
      </p>

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700 block mb-1">Montant (crédits Yukpo par utilisateur)</label>
          <input type="number" min={1} value={montant} onChange={e => setMontant(parseInt(e.target.value) || 0)}
            className="w-full border rounded-lg px-3 py-2 text-sm" />
          <p className="text-xs text-gray-400 mt-1">≈ {fmtFcfa(Math.round(montant * 0.6))} de valeur par bénéficiaire</p>
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 block mb-2">Cible</label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { v: 'tous',        lbl: 'Tous',         d: 'Utilisateurs actifs' },
              { v: 'role',        lbl: 'Par rôle',     d: 'agent, admin…' },
              { v: 'ids',         lbl: 'Liste IDs',    d: 'Utilisateurs précis' },
              { v: 'consommation',lbl: 'Consommation', d: 'Selon seuils d\'usage' },
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
            <label className="text-sm font-medium text-gray-700 block mb-1">Rôle ciblé</label>
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
            <label className="text-sm font-medium text-gray-700 block mb-1">IDs utilisateurs (séparés par virgule ou espace)</label>
            <textarea value={userIdsRaw} onChange={e => setUserIdsRaw(e.target.value)} rows={3}
              placeholder="ex: 12, 34, 56"
              className="w-full border rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        )}

        {cible === 'consommation' && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-3">
            <div className="text-sm font-medium text-gray-700">Seuils de consommation (au moins un requis)</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Crédits consommés ≥">
                <input type="number" min={0} value={seuilCreditsMin} onChange={e => setSeuilCreditsMin(e.target.value)}
                  placeholder="ex: 1000"
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
              <Field label="Crédits consommés ≤">
                <input type="number" min={0} value={seuilCreditsMax} onChange={e => setSeuilCreditsMax(e.target.value)}
                  placeholder="ex: 5000"
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
              <Field label="Nombre d'appels ≥">
                <input type="number" min={0} value={seuilAppelsMin} onChange={e => setSeuilAppelsMin(e.target.value)}
                  placeholder="ex: 50"
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
              <Field label="Période d'analyse (jours)">
                <input type="number" min={1} max={365} value={periodeJours}
                  onChange={e => setPeriodeJours(Math.max(1, parseInt(e.target.value) || 30))}
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </Field>
            </div>
          </div>
        )}

        <div>
          <label className="text-sm font-medium text-gray-700 block mb-1">Motif (audit)</label>
          <input value={motif} onChange={e => setMotif(e.target.value)}
            placeholder="ex: Promotion lancement, compensation panne du 15/05…"
            className="w-full border rounded-lg px-3 py-2 text-sm" />
        </div>

        <button type="submit" disabled={busy}
          className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-lg flex items-center gap-2">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Megaphone size={14} />}
          {busy ? 'Distribution…' : 'Lancer la campagne'}
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
