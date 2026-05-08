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

const OPERATEURS: { id: string; labelKey: string }[] = [
  { id: 'orange_money', labelKey: 'abonnement.operatorOrangeMoney' },
  { id: 'mtn_momo',     labelKey: 'abonnement.operatorMtnMomo' },
  { id: 'wave',         labelKey: 'abonnement.operatorWaveLabel' },
  { id: 'moov_money',   labelKey: 'abonnement.operatorMoovMoney' },
  { id: 'airtel_money', labelKey: 'abonnement.operatorAirtelMoney' },
  { id: 'expressunion', labelKey: 'abonnement.operatorExpressUnion' },
]

const RECHARGES_PRERELEES: { fcfa: number; descKey: string; badgeKey?: string }[] = [
  { fcfa: 1_000,  descKey: 'abonnement.presetDecouverte' },
  { fcfa: 2_000,  descKey: 'abonnement.presetPetit' },
  { fcfa: 5_000,  descKey: 'abonnement.presetRegulier', badgeKey: 'abonnement.badgePopulaire' },
  { fcfa: 10_000, descKey: 'abonnement.presetIntensif' },
  { fcfa: 25_000, descKey: 'abonnement.presetVolume' },
  { fcfa: 50_000, descKey: 'abonnement.presetPro' },
]

// Ratio aligné sur YukpoPro : 0,6 FCFA = 1 crédit Yukpo (≈ 1.667 crédits / FCFA)
const FCFA_PAR_CREDIT = 0.6
const creditsForFcfa = (fcfa: number): number => Math.floor(fcfa / FCFA_PAR_CREDIT)
const fcfaForCredits = (credits: number): number => Math.round(credits * FCFA_PAR_CREDIT)

const MODULE_LABEL_KEYS: Record<string, string> = {
  redaction:    'abonnement.modLabelRedaction',
  ocr:          'abonnement.modLabelOcr',
  audio:        'abonnement.modLabelAudio',
  traduction:   'abonnement.modLabelTraduction',
  infographie:  'abonnement.modLabelInfographie',
  designerpro:  'abonnement.modLabelDesignerPro',
  gestion:      'abonnement.modLabelGestion',
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
      toast.success(t('abonnement.paymentInitiatedToast', { amount: fmtFcfa(data.montant_fcfa), credits: fmtNb(data.credits) }))
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('abonnement.errInitiation')),
  })

  const confirmer = useMutation({
    mutationFn: async () => {
      const r = await abonnementAPI.confirmerRecharge({ reference_paiement: reference! })
      return r.data
    },
    onSuccess: () => {
      toast.success(t('abonnement.creditsAddedOk'))
      setReference(null); setInstructions(null); setPaiementOuvert(false)
      qc.invalidateQueries({ queryKey: ['bureau-mon-abonnement'] })
      qc.invalidateQueries({ queryKey: ['bureau-historique'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('abonnement.errConfirmation')),
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
              {t('abonnement.remainingUsage', { amount: fmtFcfa(fcfaForCredits(monAbo?.credits_restants ?? 0)) })}
            </div>
          </div>
          <div className="text-right">
            <div className="text-white/70 text-xs uppercase tracking-wide">{t('abonnement.totalConsumed')}</div>
            <div className="text-2xl font-bold mt-1">{fmtNb(Math.round(monAbo?.credits_utilises ?? 0))}</div>
            <div className="text-white/80 text-xs mt-1">{t('abonnement.sinceCreation')}</div>
          </div>
        </div>
        <div
          className="mt-4 text-xs text-white/70 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: t('abonnement.tariffLine', { tariff: t('abonnement.yukpoTariff') }) }}
        />
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
                  {r.badgeKey && (
                    <span className="absolute top-2 right-2 bg-amber-100 text-amber-700 text-[10px] font-semibold px-2 py-0.5 rounded-full">
                      {t(r.badgeKey)}
                    </span>
                  )}
                  <div className="text-xs text-gray-400">{t(r.descKey)}</div>
                  <div className="text-2xl font-bold text-gray-900 mt-1">{fmtFcfa(r.fcfa)}</div>
                  <div className="text-xs text-brand-600 mt-1 flex items-center gap-1">
                    <Zap size={10} /> {fmtNb(creditsForFcfa(r.fcfa))} {t('common.credits').toLowerCase()}
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
                <label className="block text-xs text-gray-500 mb-1">{t('abonnement.amountLabel')}</label>
                <input type="number" min={1000} step={500} value={montantCustom}
                  onChange={e => setMontantCustom(Math.max(1000, parseInt(e.target.value) || 1000))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div className="flex-1 w-full text-center sm:text-left">
                <div className="text-xs text-gray-500">{t('abonnement.creditsAdded')}</div>
                <div className="text-2xl font-bold text-brand-600">
                  {fmtNb(creditsAttendus)}
                </div>
                <div className="text-xs text-gray-400">{t('abonnement.usageEquivalent', { amount: fmtFcfa(montantCustom) })}</div>
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
              <Loader2 className="inline animate-spin mr-2" size={16} /> {t('common.loading')}
            </div>
          )}
          {walletQ.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
              <AlertCircle className="inline mr-2" size={14} /> {t('abonnement.errLoadStats')}
            </div>
          )}
          {walletQ.data && (
            <>
              {/* KPIs période */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label={t('abonnement.consumCreditsKpi')} value={fmtNb(walletQ.data.totaux?.credits_consommes ?? 0)} sub={t('abonnement.subLast30')} />
                <KPI label={t('abonnement.totalCalls')} value={fmtNb(walletQ.data.totaux?.appels ?? 0)} sub={t('abonnement.subLlmAndForfaits', { llm: walletQ.data.totaux?.nb_appels_llm ?? 0, forfaits: walletQ.data.totaux?.nb_forfaits ?? 0 })} />
                <KPI label={t('abonnement.valueConsumed')} value={fmtFcfa(walletQ.data.totaux?.valeur_fcfa_payee ?? 0)} sub={t('abonnement.subFcfaEquivalent')} />
                <KPI label={t('abonnement.modulesUsed')} value={fmtNb(walletQ.data.top_modules?.length ?? 0)} sub={t('abonnement.subDifferent')} />
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
                              {MODULE_LABEL_KEYS[m.module] ? t(MODULE_LABEL_KEYS[m.module]) : m.module}
                            </span>
                            <span className="text-gray-500 text-xs">
                              {t('abonnement.creditsAndCalls', { credits: fmtNb(m.credits), calls: fmtNb(m.appels), plural: m.appels > 1 ? 's' : '' })}
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
                  <p className="p-4 text-sm text-gray-500">{t('common.noConsumption')}</p>
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
                            <td className="px-3 py-2 font-medium">{MODULE_LABEL_KEYS[h.module] ? t(MODULE_LABEL_KEYS[h.module]) : h.module}</td>
                            <td className="px-3 py-2 text-gray-500">
                              {h.modele?.startsWith('forfait:') ? t('abonnement.forfaitPrefix', { name: h.modele.replace('forfait:', '') }) : h.modele || t('abonnement.fallbackYukpo')}
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
              <Loader2 className="animate-spin" size={14} /> {t('common.loading')}
            </div>
          )}
          {historiqueQ.isError && (
            <div className="p-4 text-sm text-red-600 flex items-center gap-2">
              <AlertCircle size={14} /> {t('abonnement.loadingError')}
              <button onClick={() => historiqueQ.refetch()} className="ml-2 px-2 py-1 bg-red-600 text-white rounded text-xs">
                <RefreshCw size={11} className="inline" /> {t('common.retry')}
              </button>
            </div>
          )}
          {(historiqueQ.data?.historique_recharges || []).length === 0 && !historiqueQ.isLoading && (
            <div className="p-4 text-sm text-gray-500">{t('abonnement.noRechargeYet')}</div>
          )}
          {(historiqueQ.data?.historique_recharges || []).map((h: any) => (
            <div key={h.reference} className="p-3 flex items-center justify-between text-sm">
              <div>
                <div className="font-semibold">{h.pack_nom}</div>
                <div className="text-xs text-gray-500">{t('abonnement.creditsRefSeparator', { credits: fmtNb(h.credits), ref: h.reference })}</div>
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
                {OPERATEURS.map(o => <option key={o.id} value={o.id}>{t(o.labelKey)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('abonnement.phone')}</label>
              <input value={numero} onChange={e => setNumero(e.target.value.replace(/[^0-9+]/g, ''))}
                placeholder={t('abonnement.phonePlaceholder')}
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
              <span dangerouslySetInnerHTML={{ __html: t('abonnement.modalAmount', { amount: fmtFcfa(instructions.montant_fcfa) }) }} /><br />
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
