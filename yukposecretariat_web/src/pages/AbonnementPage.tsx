import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Zap, CheckCircle2, Clock, Loader2, Package, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import { abonnementAPI } from '../api/client'
import { DemoBanner } from '../components/DemoBanner'

interface Plan {
  id: string
  nom: string
  prix_fcfa: number
  credits_mois: number
  duree_jours: number
  modules: string[]
  description: string
  label_credits: string
  badge?: string
}

interface PackCredit {
  id: string
  nom: string
  credits: number
  prix_fcfa: number
  description: string
  badge?: string
}

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
  renouvellement_le?: string | null
}

const OPERATEURS = [
  { id: 'orange_money', label: 'Orange Money' },
  { id: 'mtn_momo', label: 'MTN MoMo' },
  { id: 'wave', label: 'Wave' },
  { id: 'moov_money', label: 'Moov Money' },
  { id: 'airtel_money', label: 'Airtel Money' },
  { id: 'expressunion', label: 'Express Union' },
]

const MODULE_LABELS: Record<string, string> = {
  redaction: 'Rédaction IA',
  ocr: 'Scan / OCR',
  audio: 'Audio → Doc',
  traduction: 'Traduction',
  infographie: 'Infographie',
  gestion: 'Gestion',
  documents: 'Mes Documents',
}

function fmtFcfa(n: number): string {
  return n.toLocaleString('fr-FR') + ' FCFA'
}

export default function AbonnementPage() {
  const qc = useQueryClient()
  const [onglet, setOnglet] = useState<'plans' | 'recharge' | 'historique'>('plans')
  const [planChoisi, setPlanChoisi] = useState<string | null>(null)
  const [packChoisi, setPackChoisi] = useState<string | null>(null)
  const [operateur, setOperateur] = useState('orange_money')
  const [numero, setNumero] = useState('')
  const [reference, setReference] = useState<string | null>(null)
  const [instructions, setInstructions] = useState<any>(null)
  const [typeEnAttente, setTypeEnAttente] = useState<'plan' | 'recharge' | null>(null)

  const { data: monAbo } = useQuery<MonAbonnement>({
    queryKey: ['bureau-mon-abonnement'],
    queryFn: () => abonnementAPI.monAbonnement().then(r => r.data),
    refetchOnWindowFocus: true,
  })

  const { data: plansData } = useQuery<{ plans: Plan[] }>({
    queryKey: ['bureau-plans'],
    queryFn: () => abonnementAPI.plans().then(r => r.data),
  })

  const { data: packsData } = useQuery<{ packs: PackCredit[] }>({
    queryKey: ['bureau-packs'],
    queryFn: () => abonnementAPI.packsCredits().then(r => r.data),
  })

  const { data: historique } = useQuery({
    queryKey: ['bureau-historique'],
    queryFn: () => abonnementAPI.historique().then(r => r.data),
    enabled: onglet === 'historique',
  })

  const initierPaiement = useMutation({
    mutationFn: () =>
      abonnementAPI.initier({ plan: planChoisi!, operateur, numero_telephone: numero }).then(r => r.data),
    onSuccess: data => {
      setReference(data.reference)
      setInstructions(data.instructions)
      setTypeEnAttente('plan')
      toast.success(`Paiement initié : ${data.reference}`)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Erreur initiation'),
  })

  const confirmerPaiement = useMutation({
    mutationFn: () => abonnementAPI.confirmer({ reference_paiement: reference! }).then(r => r.data),
    onSuccess: () => {
      toast.success('Abonnement activé !')
      setReference(null); setInstructions(null); setPlanChoisi(null); setTypeEnAttente(null)
      qc.invalidateQueries({ queryKey: ['bureau-mon-abonnement'] })
      qc.invalidateQueries({ queryKey: ['bureau-historique'] })
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Erreur confirmation'),
  })

  const initierRecharge = useMutation({
    mutationFn: () =>
      abonnementAPI.initierRecharge({ pack_id: packChoisi!, operateur, numero_telephone: numero }).then(r => r.data),
    onSuccess: data => {
      setReference(data.reference)
      setInstructions(data.instructions)
      setTypeEnAttente('recharge')
      toast.success(`Recharge initiée : ${data.reference}`)
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Erreur recharge'),
  })

  const confirmerRecharge = useMutation({
    mutationFn: () => abonnementAPI.confirmerRecharge({ reference_paiement: reference! }).then(r => r.data),
    onSuccess: () => {
      toast.success('Crédits ajoutés !')
      setReference(null); setInstructions(null); setPackChoisi(null); setTypeEnAttente(null)
      qc.invalidateQueries({ queryKey: ['bureau-mon-abonnement'] })
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Erreur confirmation'),
  })

  return (
    <div className="space-y-6">
      <DemoBanner />
      <header className="flex items-center gap-3">
        <CreditCard className="text-brand-600" size={28} />
        <div>
          <h1 className="text-2xl font-bold">Abonnement & Crédits</h1>
          <p className="text-sm text-gray-500">Gérez votre plan et rechargez vos crédits Yukpo</p>
        </div>
      </header>

      {monAbo && (
        <div className="bg-gradient-to-br from-brand-600 to-brand-700 text-white rounded-2xl p-6 shadow-lg">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-brand-100 text-xs uppercase tracking-wide">Plan actif</div>
              <div className="text-3xl font-bold mt-1">{monAbo.nom_plan}</div>
              <div className="text-brand-200 text-sm mt-1">{monAbo.label_credits}</div>
            </div>
            <div className="text-right">
              <div className="text-brand-100 text-xs uppercase tracking-wide">Crédits restants</div>
              <div className="text-3xl font-bold mt-1">{Math.round(monAbo.credits_restants).toLocaleString('fr-FR')}</div>
              <div className="text-brand-200 text-sm mt-1">sur {monAbo.credits_alloues.toLocaleString('fr-FR')}</div>
            </div>
          </div>
          <div className="mt-4 bg-white/20 rounded-full h-2 overflow-hidden">
            <div
              className="bg-white h-full transition-all"
              style={{ width: `${Math.min(100, monAbo.pct_utilise)}%` }}
            />
          </div>
          <div className="flex flex-wrap gap-2 mt-4">
            {monAbo.modules_autorises?.map(m => (
              <span key={m} className="bg-white/20 rounded-full px-3 py-1 text-xs">
                {MODULE_LABELS[m] || m}
              </span>
            ))}
          </div>
          {monAbo.renouvellement_le && (
            <div className="text-brand-200 text-xs mt-3 flex items-center gap-1">
              <Clock size={12} /> Renouvellement : {monAbo.renouvellement_le}
            </div>
          )}
        </div>
      )}

      <nav className="flex gap-2 border-b">
        {([
          ['plans', 'Plans'],
          ['recharge', 'Recharger des crédits'],
          ['historique', 'Historique'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setOnglet(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              onglet === key
                ? 'border-brand-600 text-brand-600'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {onglet === 'plans' && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {plansData?.plans.map(p => (
            <div
              key={p.id}
              className={`bg-white rounded-xl p-5 border-2 transition ${
                planChoisi === p.id ? 'border-brand-500 shadow-lg' : 'border-gray-200 hover:border-brand-300'
              }`}
            >
              {p.badge && (
                <span className="inline-block bg-brand-100 text-brand-700 text-xs px-2 py-0.5 rounded-full mb-2">
                  {p.badge}
                </span>
              )}
              <h3 className="text-xl font-bold">{p.nom}</h3>
              <div className="text-3xl font-bold text-brand-600 mt-2">
                {p.prix_fcfa === 0 ? 'Gratuit' : fmtFcfa(p.prix_fcfa)}
                {p.prix_fcfa > 0 && <span className="text-sm text-gray-500 font-normal"> / mois</span>}
              </div>
              <div className="text-sm text-gray-600 mt-2">{p.description}</div>
              <div className="text-sm text-brand-700 font-semibold mt-3 flex items-center gap-1">
                <Zap size={14} /> {p.label_credits}
              </div>
              <div className="flex flex-wrap gap-1 mt-3">
                {p.modules.map(m => (
                  <span key={m} className="bg-gray-100 text-gray-700 text-[10px] px-2 py-0.5 rounded-full">
                    {MODULE_LABELS[m] || m}
                  </span>
                ))}
              </div>
              {p.id !== 'gratuit' && (
                <button
                  onClick={() => setPlanChoisi(p.id)}
                  disabled={monAbo?.plan === p.id}
                  className="w-full mt-4 bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 text-white rounded-lg py-2 text-sm font-semibold transition"
                >
                  {monAbo?.plan === p.id ? 'Plan actuel' : 'Choisir ce plan'}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {onglet === 'recharge' && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {packsData?.packs.map(p => (
            <div
              key={p.id}
              className={`bg-white rounded-xl p-5 border-2 transition ${
                packChoisi === p.id ? 'border-brand-500 shadow-lg' : 'border-gray-200 hover:border-brand-300'
              }`}
            >
              {p.badge && (
                <span className="inline-block bg-amber-100 text-amber-700 text-xs px-2 py-0.5 rounded-full mb-2">
                  {p.badge}
                </span>
              )}
              <Package className="text-brand-500 mb-2" size={24} />
              <h3 className="font-bold">{p.nom}</h3>
              <div className="text-2xl font-bold text-brand-600 mt-1">
                {p.credits.toLocaleString('fr-FR')} <span className="text-xs font-normal text-gray-500">crédits</span>
              </div>
              <div className="text-lg font-semibold text-gray-800 mt-1">{fmtFcfa(p.prix_fcfa)}</div>
              <button
                onClick={() => setPackChoisi(p.id)}
                className="w-full mt-3 bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2 text-sm font-semibold"
              >
                <Plus size={14} className="inline -mt-0.5 mr-1" />
                Acheter
              </button>
            </div>
          ))}
        </div>
      )}

      {onglet === 'historique' && (
        <div className="space-y-4">
          <section>
            <h3 className="text-lg font-semibold mb-2">Abonnements</h3>
            <div className="bg-white border rounded-lg divide-y">
              {(historique?.historique_abonnements || []).length === 0 && (
                <div className="p-4 text-sm text-gray-500">Aucun abonnement passé.</div>
              )}
              {(historique?.historique_abonnements || []).map((h: any) => (
                <div key={h.reference} className="p-3 flex items-center justify-between text-sm">
                  <div>
                    <div className="font-semibold capitalize">{h.plan}</div>
                    <div className="text-xs text-gray-500">{h.operateur} · {h.reference}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold">{fmtFcfa(h.montant_fcfa)}</div>
                    <div className="text-xs text-gray-500">{new Date(h.date).toLocaleDateString('fr-FR')}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h3 className="text-lg font-semibold mb-2">Recharges de crédits</h3>
            <div className="bg-white border rounded-lg divide-y">
              {(historique?.historique_recharges || []).length === 0 && (
                <div className="p-4 text-sm text-gray-500">Aucune recharge passée.</div>
              )}
              {(historique?.historique_recharges || []).map((h: any) => (
                <div key={h.reference} className="p-3 flex items-center justify-between text-sm">
                  <div>
                    <div className="font-semibold">{h.pack_nom}</div>
                    <div className="text-xs text-gray-500">{h.credits.toLocaleString('fr-FR')} crédits · {h.reference}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold">{fmtFcfa(h.montant)}</div>
                    <div className="text-xs text-gray-500">{h.date}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* Modal paiement */}
      {(planChoisi || packChoisi) && !reference && (
        <div className="fixed inset-0 z-40 bg-black/50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-t-2xl md:rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-lg font-bold">
              Paiement {planChoisi ? `: ${plansData?.plans.find(p => p.id === planChoisi)?.nom}` : `: ${packsData?.packs.find(p => p.id === packChoisi)?.nom}`}
            </h3>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Opérateur Mobile Money</label>
              <select
                value={operateur}
                onChange={e => setOperateur(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm"
              >
                {OPERATEURS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Numéro de téléphone</label>
              <input
                value={numero}
                onChange={e => setNumero(e.target.value.replace(/[^0-9+]/g, ''))}
                placeholder="ex: 690000001"
                className="w-full border rounded-lg px-3 py-2 text-sm"
              />
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setPlanChoisi(null); setPackChoisi(null) }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
              >
                Annuler
              </button>
              <button
                onClick={() => planChoisi ? initierPaiement.mutate() : initierRecharge.mutate()}
                disabled={!numero || numero.length < 8 || initierPaiement.isPending || initierRecharge.isPending}
                className="bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 text-white rounded-lg px-4 py-2 text-sm font-semibold"
              >
                {(initierPaiement.isPending || initierRecharge.isPending)
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
              Paiement initié — Référence : {reference}
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
              <button
                onClick={() => { setReference(null); setInstructions(null); setTypeEnAttente(null); setPlanChoisi(null); setPackChoisi(null) }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
              >
                Fermer
              </button>
              <button
                onClick={() => typeEnAttente === 'plan' ? confirmerPaiement.mutate() : confirmerRecharge.mutate()}
                disabled={confirmerPaiement.isPending || confirmerRecharge.isPending}
                className="bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white rounded-lg px-4 py-2 text-sm font-semibold"
              >
                {(confirmerPaiement.isPending || confirmerRecharge.isPending)
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
