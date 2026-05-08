import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Zap, CheckCircle2, Loader2, Plus, AlertCircle, RefreshCw, Wallet } from 'lucide-react'
import toast from 'react-hot-toast'
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

const MULTIPLICATEUR = 20  // 1 FCFA = 20 crédits Yukpo

function fmtFcfa(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('fr-FR') + ' FCFA'
}
function fmtNb(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('fr-FR')
}

export default function AbonnementPage() {
  const qc = useQueryClient()
  const [onglet, setOnglet] = useState<'recharge' | 'historique'>('recharge')
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

  const creditsAttendus = montantCustom * MULTIPLICATEUR

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <Wallet className="text-brand-600" size={28} />
        <div>
          <h1 className="text-2xl font-bold">Crédits</h1>
          <p className="text-sm text-gray-500">Pay-as-you-go — rechargez votre solde à la demande, pas d'abonnement</p>
        </div>
      </header>

      {/* Solde */}
      <div className="bg-gradient-to-br from-brand-600 to-brand-700 text-white rounded-2xl p-6 shadow-lg">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <div className="text-white/70 text-xs uppercase tracking-wide">Solde actuel</div>
            <div className="text-4xl font-bold mt-1">
              {fmtNb(Math.round(monAbo?.credits_restants ?? 0))}
              <span className="text-base font-normal text-white/70 ml-1">crédits</span>
            </div>
            <div className="text-white/80 text-sm mt-1">
              ≈ {fmtFcfa(Math.round((monAbo?.credits_restants ?? 0) / MULTIPLICATEUR))} d'usage
            </div>
          </div>
          <div className="text-right">
            <div className="text-white/70 text-xs uppercase tracking-wide">Total consommé</div>
            <div className="text-2xl font-bold mt-1">{fmtNb(Math.round(monAbo?.credits_utilises ?? 0))}</div>
            <div className="text-white/80 text-xs mt-1">depuis création du compte</div>
          </div>
        </div>
        <div className="mt-4 text-xs text-white/70 leading-relaxed">
          🔄 Tarification : <strong>1 FCFA = {MULTIPLICATEUR} crédits Yukpo</strong> ·
          minimum recharge 1 000 FCFA · les crédits ne périment jamais.
        </div>
      </div>

      <nav className="flex gap-2 border-b">
        {([
          ['recharge',   'Recharger des crédits'],
          ['historique', 'Historique'],
        ] as const).map(([key, label]) => (
          <button key={key} onClick={() => setOnglet(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              onglet === key ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}>
            {label}
          </button>
        ))}
      </nav>

      {/* Recharge */}
      {onglet === 'recharge' && !paiementOuvert && (
        <div className="space-y-4">
          {/* Recharges préréglées */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Recharges rapides</h2>
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
                    <Zap size={10} /> {fmtNb(r.fcfa * MULTIPLICATEUR)} crédits
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Recharge libre */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Recharge personnalisée</h2>
            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
              <div className="flex-1 w-full">
                <label className="block text-xs text-gray-500 mb-1">Montant (FCFA, minimum 1 000)</label>
                <input type="number" min={1000} step={500} value={montantCustom}
                  onChange={e => setMontantCustom(Math.max(1000, parseInt(e.target.value) || 1000))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div className="flex-1 w-full text-center sm:text-left">
                <div className="text-xs text-gray-500">Crédits ajoutés</div>
                <div className="text-2xl font-bold text-brand-600">
                  {fmtNb(creditsAttendus)}
                </div>
                <div className="text-xs text-gray-400">≈ {fmtFcfa(montantCustom)} d'usage</div>
              </div>
              <button onClick={() => setPaiementOuvert(true)} disabled={montantCustom < 1000}
                className="bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 text-white rounded-lg px-5 py-2.5 text-sm font-semibold flex items-center gap-1.5">
                <Plus size={14} /> Recharger
              </button>
            </div>
          </div>
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
            <h3 className="text-lg font-bold">Recharger {fmtFcfa(montantCustom)}</h3>
            <div className="bg-brand-50 border border-brand-200 rounded-lg p-3 text-sm flex items-center justify-between">
              <span className="text-gray-600">Crédits qui seront ajoutés</span>
              <span className="text-xl font-bold text-brand-700">{fmtNb(creditsAttendus)}</span>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Opérateur Mobile Money</label>
              <select value={operateur} onChange={e => setOperateur(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm">
                {OPERATEURS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Numéro de téléphone</label>
              <input value={numero} onChange={e => setNumero(e.target.value.replace(/[^0-9+]/g, ''))}
                placeholder="ex: 690000001"
                className="w-full border rounded-lg px-3 py-2 text-sm" />
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setPaiementOuvert(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">Annuler</button>
              <button onClick={() => initier.mutate()}
                disabled={!numero || numero.length < 8 || initier.isPending}
                className="bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 text-white rounded-lg px-4 py-2 text-sm font-semibold">
                {initier.isPending
                  ? <><Loader2 className="inline animate-spin mr-1" size={14}/>Initiation…</>
                  : 'Initier le paiement'}
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
              Paiement initié — Réf. {reference}
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
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">Fermer</button>
              <button onClick={() => confirmer.mutate()} disabled={confirmer.isPending}
                className="bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white rounded-lg px-4 py-2 text-sm font-semibold">
                {confirmer.isPending
                  ? <><Loader2 className="inline animate-spin mr-1" size={14}/>Validation…</>
                  : "J'ai payé — Confirmer"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
