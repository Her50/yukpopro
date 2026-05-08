import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Zap, CheckCircle2, Loader2, Plus, AlertCircle, RefreshCw, Wallet, BarChart3, Clock, TrendingUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { abonnementAPI } from '../api/client'

interface MonAbonnement {
  plan: string
  nom_plan: string
  statut: string
  credits_alloues: number
  credits_utilises: number
  credits_restants: number
  pct_utilise: number
  label_credits: string
  modules_autorises: string[]
  date_fin: string | null
  prix_fcfa: number
}

const OPERATEURS = [
  { id: 'orange_money', label: 'Orange Money' },
  { id: 'mtn_momo',     label: 'MTN MoMo' },
  { id: 'wave',         label: 'Wave' },
  { id: 'moov_money',   label: 'Moov Money' },
  { id: 'airtel_money', label: 'Airtel Money' },
  { id: 'expressunion', label: 'Express Union' },
]

const RECHARGES_PRERELEES = [
  { fcfa: 1_000,  desc: 'Découverte' },
  { fcfa: 2_000,  desc: 'Petit usage' },
  { fcfa: 5_000,  desc: 'Usage régulier', badge: 'Populaire' },
  { fcfa: 10_000, desc: 'Travail intensif' },
  { fcfa: 25_000, desc: 'Volume élevé' },
  { fcfa: 50_000, desc: 'Pro' },
]

// Ratio aligné sur YukpoPro : 0,6 FCFA = 1 crédit Yukpo (≈ 1.667 crédits / FCFA)
const FCFA_PAR_CREDIT = 0.6
const creditsForFcfa = (fcfa: number): number => Math.floor(fcfa / FCFA_PAR_CREDIT)
const fcfaForCredits = (credits: number): number => Math.round(credits * FCFA_PAR_CREDIT)

const MODULE_LABELS: Record<string, string> = {
  redaction:    'Rédaction Yukpo',
  ocr:          'Scan / OCR',
  audio:        'Audio Yukpo',
  traduction:   'Traduction Yukpo',
  infographie:  'Infographie',
  designerpro:  'Designer Pro',
  gestion:      'Gestion (Kanban/Devis/Caisse)',
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

export default function AbonnementPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [onglet, setOnglet] = useState<'recharge' | 'consommation' | 'historique'>('recharge')
  const [montantCustom, setMontantCustom] = useState<number>(1000)
  const [operateur, setOperateur] = useState('orange_money')
  const [numero, setNumero] = useState('')
  const [reference, setReference] = useState<string | null>(null)
  const [instructions, setInstructions] = useState<any>(null)
  const [paiementOuvert, setPaiementOuvert] = useState(false)

  const monAboQ = useQuery<MonAbonnement>({
    queryKey: ['bureau-mon-abonnement'],
    queryFn: async () => {
      const r = await abonnementAPI.monAbonnement()
      return r.data as MonAbonnement
    },
    refetchOnWindowFocus: true,
    retry: 1,
  })
  const monAbo = monAboQ.data

  const historiqueQ = useQuery({
    queryKey: ['bureau-historique'],
    queryFn: async () => {
      const r = await abonnementAPI.historique()
      return r.data
    },
    enabled: onglet === 'historique',
    retry: 1,
  })

  const walletQ = useQuery({
    queryKey: ['bureau-wallet'],
    queryFn: async () => {
      const r = await abonnementAPI.wallet(30)
      return r.data
    },
    enabled: onglet === 'consommation',
    retry: 1,
  })

  const initier = useMutation({
    mutationFn: async () => {
      const r = await abonnementAPI.initierRechargeCustom({
        montant_fcfa: montantCustom, operateur, numero_telephone: numero,
      })
      return r.data
    },
    onSuccess: (data: any) => {
      setReference(data.reference)
      setInstructions(data.instructions)
      toast.success(`Paiement initié — ${fmtFcfa(data.montant_fcfa)} = ${fmtNb(data.credits)} crédits`)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Erreur initiation'),
  })

  const confirmer = useMutation({
    mutationFn: async () => {
      const r = await abonnementAPI.confirmerRecharge({ reference_paiement: reference! })
      return r.data
    },
    onSuccess: () => {
      toast.success('Crédits ajoutés ✓')
      setReference(null); setInstructions(null); setPaiementOuvert(false)
      qc.invalidateQueries({ queryKey: ['bureau-mon-abonnement'] })
      qc.invalidateQueries({ queryKey: ['bureau-historique'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Erreur confirmation'),
  })

  const creditsAttendus = creditsForFcfa(montantCustom)

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <Wallet className="text-brand-600" size={28} />
        <div>
          <h1 className="text-2xl font-bold">{t('abonnement.title')}</h1>
          <p className="text-sm text-gray-500">{t('abonnement.subtitle')}</p>
        </div>
      </header>

      {/* Solde */}
      <div className="bg-gradient-to-br from-brand-600 to-brand-700 text-white rounded-2xl p-6 shadow-lg">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div className="text-white/70 text-xs uppercase tracking-wide">{t('abonnement.currentBalance')}</div>
            <div className="text-4xl font-bold mt-1">
              {fmtNb(Math.round(monAbo?.credits_restants ?? 0))}
              <span className="text-base font-normal text-white/70 ml-1">{t('abonnement.creditsYukpo')}</span>
            </div>
            <div className="text-white/80 text-sm mt-1">
              ≈ {fmtFcfa(fcfaForCredits(monAbo?.credits_restants ?? 0))} d'usage restant
            </div>
          </div>
          <div className="text-right">
            <div className="text-white/70 text-xs uppercase tracking-wide">{t('abonnement.totalConsumed')}</div>
            <div className="text-2xl font-bold mt-1">{fmtNb(Math.round(monAbo?.credits_utilises ?? 0))}</div>
            <div className="text-white/80 text-xs mt-1">depuis création du compte</div>
          </div>
        </div>
        <div className="mt-4 text-xs text-white/70 leading-relaxed">
          🔄 {t('abonnement.yukpoTariff')} : <strong>0,6 FCFA = 1 crédit</strong> · minimum recharge
          1 000 FCFA · vos crédits ne périment jamais.
        </div>
      </div>

      <nav className="flex gap-2 border-b overflow-x-auto">
        {([
          ['recharge',     t('abonnement.tabPacks'),     Plus],
          ['consommation', t('abonnement.consumption'),  BarChart3],
          ['historique',   t('abonnement.tabHistory'),   Clock],
        ] as const).map(([key, label, Icon]) => (
          <button key={key} onClick={() => setOnglet(key as any)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition flex items-center gap-1.5 whitespace-nowrap ${
              onglet === key ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </nav>

      {/* Recharge */}
      {onglet === 'recharge' && !paiementOuvert && (
        <div className="space-y-4">
          {/* Recharges préréglées */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">{t('abonnement.quickRecharges')}</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {RECHARGES_PRERELEES.map(r => (
                <button key={r.fcfa}
                  onClick={() => { setMontantCustom(r.fcfa); setPaiementOuvert(true) }}
                  className={`relative bg-white rounded-xl p-4 border-2 hover:border-brand-500 hover:shadow-md transition text-left ${
                    montantCustom === r.fcfa ? 'border-brand-500 shadow' : 'border-gray-200'
                  }`}>
                  {r.badge && (
                    <span className="absolute top-2 right-2 bg-amber-100 text-amber-700 text-[10px] font-semibold px-2 py-0.5 rounded-full">
                      {r.badge}
                    </span>
                  )}
                  <div className="text-xs text-gray-400">{r.desc}</div>
                  <div className="text-2xl font-bold text-gray-900 mt-1">{fmtFcfa(r.fcfa)}</div>
                  <div className="text-xs text-brand-600 mt-1 flex items-center gap-1">
                    <Zap size={10} /> {fmtNb(creditsForFcfa(r.fcfa))} crédits
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Recharge libre */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">{t('abonnement.customRecharge')}</h2>
            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
              <div className="flex-1 w-full">
                <label className="block text-xs text-gray-500 mb-1">Montant (FCFA, minimum 1 000)</label>
                <input type="number" min={1000} step={500} value={montantCustom}
                  onChange={e => setMontantCustom(Math.max(1000, parseInt(e.target.value) || 1000))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div className="flex-1 w-full text-center sm:text-left">
                <div className="text-xs text-gray-500">{t('abonnement.creditsAdded')}</div>
                <div className="text-2xl font-bold text-brand-600">
                  {fmtNb(creditsAttendus)}
                </div>
                <div className="text-xs text-gray-400">≈ {fmtFcfa(montantCustom)} d'usage</div>
              </div>
              <button onClick={() => setPaiementOuvert(true)} disabled={montantCustom < 1000}
                className="bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 text-white rounded-lg px-5 py-2.5 text-sm font-semibold flex items-center gap-1.5">
                <Plus size={14} /> {t('abonnement.buy')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Consommation détaillée (30 derniers jours) */}
      {onglet === 'consommation' && (
        <div className="space-y-4">
          {walletQ.isLoading && (
            <div className="text-center py-8 text-gray-500">
              <Loader2 className="inline animate-spin mr-2" size={16} /> Chargement…
            </div>
          )}
          {walletQ.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
              <AlertCircle className="inline mr-2" size={14} /> Impossible de charger les statistiques
            </div>
          )}
          {walletQ.data && (
            <>
              {/* KPIs période */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label={t('abonnement.consumCreditsKpi')} value={fmtNb(walletQ.data.totaux?.credits_consommes ?? 0)} sub="30 derniers jours" />
                <KPI label={t('abonnement.totalCalls')} value={fmtNb(walletQ.data.totaux?.appels ?? 0)} sub={`${walletQ.data.totaux?.nb_appels_llm ?? 0} LLM · ${walletQ.data.totaux?.nb_forfaits ?? 0} forfaits`} />
                <KPI label={t('abonnement.valueConsumed')} value={fmtFcfa(walletQ.data.totaux?.valeur_fcfa_payee ?? 0)} sub="≈ équivalent FCFA" />
                <KPI label={t('abonnement.modulesUsed')} value={fmtNb(walletQ.data.top_modules?.length ?? 0)} sub="différents" />
              </div>

              {/* Top modules consommateurs */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <TrendingUp size={14} className="text-brand-600" /> {t('abonnement.topConsumers')}
                </h3>
                {(walletQ.data.top_modules || []).length === 0 ? (
                  <p className="text-sm text-gray-500">{t('abonnement.noConsumPeriod')}</p>
                ) : (
                  <div className="space-y-2">
                    {walletQ.data.top_modules.map((m: any) => {
                      const total = walletQ.data.totaux?.credits_consommes || 1
                      const pct = (m.credits / total) * 100
                      return (
                        <div key={m.module}>
                          <div className="flex items-center justify-between text-sm">
                            <span className="font-medium text-gray-700">
                              {MODULE_LABELS[m.module] || m.module}
                            </span>
                            <span className="text-gray-500 text-xs">
                              {fmtNb(m.credits)} crédits · {fmtNb(m.appels)} appel{m.appels > 1 ? 's' : ''}
                            </span>
                          </div>
                          <div className="bg-gray-100 rounded-full h-2 mt-1 overflow-hidden">
                            <div className="bg-brand-500 h-full transition-all" style={{ width: `${Math.max(2, pct)}%` }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Historique récent */}
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <h3 className="text-sm font-semibold text-gray-700 p-4 border-b">
                  {t('abonnement.recentHistory')}
                </h3>
                {(walletQ.data.historique || []).length === 0 ? (
                  <p className="p-4 text-sm text-gray-500">Aucune consommation.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 text-gray-500 uppercase">
                        <tr>
                          <th className="text-left px-3 py-2 font-semibold">{t('abonnement.headerDate')}</th>
                          <th className="text-left px-3 py-2 font-semibold">{t('abonnement.headerModule')}</th>
                          <th className="text-left px-3 py-2 font-semibold">{t('abonnement.headerType')}</th>
                          <th className="text-right px-3 py-2 font-semibold">{t('abonnement.headerTokens')}</th>
                          <th className="text-right px-3 py-2 font-semibold">{t('abonnement.headerCredits')}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {walletQ.data.historique.slice(0, 50).map((h: any) => (
                          <tr key={h.id} className="hover:bg-gray-50">
                            <td className="px-3 py-2 text-gray-500">
                              {h.date ? new Date(h.date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                            </td>
                            <td className="px-3 py-2 font-medium">{MODULE_LABELS[h.module] || h.module}</td>
                            <td className="px-3 py-2 text-gray-500">
                              {h.modele?.startsWith('forfait:') ? `Forfait ${h.modele.replace('forfait:', '')}` : h.modele || 'Yukpo'}
                            </td>
                            <td className="px-3 py-2 text-right text-gray-500">
                              {h.tokens_input + h.tokens_output > 0 ? fmtNb(h.tokens_input + h.tokens_output) : '—'}
                            </td>
                            <td className="px-3 py-2 text-right font-semibold text-brand-700">
                              {fmtNb(h.credits_debites)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Historique */}
      {onglet === 'historique' && (
        <div className="bg-white border rounded-xl divide-y">
          {historiqueQ.isLoading && (
            <div className="p-4 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 className="animate-spin" size={14} /> Chargement…
            </div>
          )}
          {historiqueQ.isError && (
            <div className="p-4 text-sm text-red-600 flex items-center gap-2">
              <AlertCircle size={14} /> Impossible de charger l'historique
              <button onClick={() => historiqueQ.refetch()} className="ml-2 px-2 py-1 bg-red-600 text-white rounded text-xs">
                <RefreshCw size={11} className="inline" /> Réessayer
              </button>
            </div>
          )}
          {(historiqueQ.data?.historique_recharges || []).length === 0 && !historiqueQ.isLoading && (
            <div className="p-4 text-sm text-gray-500">Aucune recharge effectuée.</div>
          )}
          {(historiqueQ.data?.historique_recharges || []).map((h: any) => (
            <div key={h.reference} className="p-3 flex items-center justify-between text-sm">
              <div>
                <div className="font-semibold">{h.pack_nom}</div>
                <div className="text-xs text-gray-500">{fmtNb(h.credits)} crédits · {h.reference}</div>
              </div>
              <div className="text-right">
                <div className="font-semibold">{fmtFcfa(h.montant)}</div>
                <div className="text-xs text-gray-500">{h.date}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal paiement */}
      {paiementOuvert && !reference && (
        <div className="fixed inset-0 z-40 bg-black/50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-t-2xl md:rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-lg font-bold">{t('abonnement.rechargeAmount', { amount: fmtFcfa(montantCustom) })}</h3>
            <div className="bg-brand-50 border border-brand-200 rounded-lg p-3 text-sm flex items-center justify-between">
              <span className="text-gray-600">{t('abonnement.creditsToBeAdded')}</span>
              <span className="text-xl font-bold text-brand-700">{fmtNb(creditsAttendus)}</span>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('abonnement.operator')}</label>
              <select value={operateur} onChange={e => setOperateur(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm">
                {OPERATEURS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('abonnement.phone')}</label>
              <input value={numero} onChange={e => setNumero(e.target.value.replace(/[^0-9+]/g, ''))}
                placeholder="ex: 690000001"
                className="w-full border rounded-lg px-3 py-2 text-sm" />
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setPaiementOuvert(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">{t('common.cancel')}</button>
              <button onClick={() => initier.mutate()}
                disabled={!numero || numero.length < 8 || initier.isPending}
                className="bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 text-white rounded-lg px-4 py-2 text-sm font-semibold">
                {initier.isPending
                  ? <><Loader2 className="inline animate-spin mr-1" size={14}/>{t('abonnement.initiating')}</>
                  : t('abonnement.buy')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal instructions + confirmation */}
      {reference && instructions && (
        <div className="fixed inset-0 z-40 bg-black/50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-t-2xl md:rounded-2xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <CheckCircle2 className="text-green-500" size={22} />
              {t('abonnement.paymentInitiatedRef', { ref: reference })}
            </h3>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-900">
              <strong>Montant :</strong> {fmtFcfa(instructions.montant_fcfa)}<br />
              <strong>{instructions.important}</strong>
            </div>
            <div className="space-y-2 text-sm">
              {Object.entries(instructions.etapes || {}).map(([k, v]) => (
                <div key={k} className="border rounded-lg p-3">
                  <div className="font-semibold capitalize text-brand-600 mb-1">{k}</div>
                  <div className="text-gray-700">{String(v)}</div>
                </div>
              ))}
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <button onClick={() => { setReference(null); setInstructions(null); setPaiementOuvert(false) }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">{t('common.close')}</button>
              <button onClick={() => confirmer.mutate()} disabled={confirmer.isPending}
                className="bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white rounded-lg px-4 py-2 text-sm font-semibold">
                {confirmer.isPending
                  ? <><Loader2 className="inline animate-spin mr-1" size={14}/>{t('abonnement.confirming')}</>
                  : t('abonnement.confirmPayment')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function KPI({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-3">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-xl font-bold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-[10px] text-gray-400 mt-0.5">{sub}</div>}
    </div>
  )
}
