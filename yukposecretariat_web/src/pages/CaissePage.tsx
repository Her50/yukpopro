import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Wallet, Plus, TrendingUp, TrendingDown, X, Loader2 } from 'lucide-react'
import { gestionAPI } from '../api/client'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'
import { useTranslation } from 'react-i18next'
import { DemoBanner } from '../components/DemoBanner'

const MODES_PAIEMENT = [
  { code: 'especes', label: '💵 Espèces' },
  { code: 'orange_money', label: '🟠 Orange Money' },
  { code: 'mtn_momo', label: '🟡 MTN MoMo' },
  { code: 'virement', label: '🏦 Virement' },
  { code: 'cheque', label: '📄 Chèque' },
]

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

interface Transaction {
  id: number; type: string; montant_fcfa: number; libelle: string;
  mode_paiement: string; horodatage: string
}

export default function CaissePage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const today = format(new Date(), 'yyyy-MM-dd')
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({
    type: 'entree', montant_fcfa: 0, libelle: '', mode_paiement: 'especes',
  })

  const { data, isLoading } = useQuery({
    queryKey: ['caisse', today],
    queryFn: () => gestionAPI.transactions(today).then(r => r.data),
  })

  const ajouterMutation = useMutation({
    mutationFn: (d: typeof form) => gestionAPI.enregistrerTransaction(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['caisse'] })
      setShowModal(false)
      setForm({ type: 'entree', montant_fcfa: 0, libelle: '', mode_paiement: 'especes' })
      toast.success(t('caisse.saved'))
    },
    onError: () => toast.error(t('caisse.errSave')),
  })

  const rapport = data?.rapport ?? {}
  const transactions: Transaction[] = data?.transactions ?? []

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Wallet className="text-emerald-600" size={24} />
            {t('caisse.title')}
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            {format(new Date(), 'EEEE d MMMM yyyy', { locale: fr })}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-2.5 rounded-xl text-sm"
        >
          <Plus size={18} /> {t('caisse.newTx')}
        </button>
      </div>

      {/* Solde du jour */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="bg-green-50 border border-green-200 rounded-2xl p-4">
          <div className="flex items-center gap-1.5 text-green-600 text-xs font-medium mb-1">
            <TrendingUp size={14} /> {t('caisse.income')}
          </div>
          <div className="text-base sm:text-lg font-bold text-green-700 truncate">{formatFCFA(rapport.total_entrees ?? 0)}</div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4">
          <div className="flex items-center gap-1.5 text-red-500 text-xs font-medium mb-1">
            <TrendingDown size={14} /> {t('caisse.expense')}
          </div>
          <div className="text-base sm:text-lg font-bold text-red-600 truncate">{formatFCFA(rapport.total_sorties ?? 0)}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-2xl p-4 col-span-2 sm:col-span-1">
          <div className="text-xs font-medium text-gray-500 mb-1">{t('caisse.balance')}</div>
          <div className={`text-base sm:text-lg font-bold truncate ${(rapport.solde ?? 0) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            {formatFCFA(rapport.solde ?? 0)}
          </div>
        </div>
      </div>

      {/* Répartition modes */}
      {rapport.repartition?.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">{t('caisse.paymentMethodBreakdown')}</h3>
          <div className="space-y-2">
            {rapport.repartition.map((r: { mode: string; montant: number; pourcentage: number }) => (
              <div key={r.mode}>
                <div className="flex justify-between text-xs text-gray-600 mb-1">
                  <span>{MODES_PAIEMENT.find(m => m.code === r.mode)?.label ?? r.mode}</span>
                  <span>{formatFCFA(r.montant)} ({r.pourcentage}%)</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full"
                    style={{ width: `${r.pourcentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Liste transactions */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">{t('caisse.txOfDay', { n: transactions.length })}</h2>
        {isLoading ? (
          <div className="flex justify-center py-8"><Loader2 size={22} className="animate-spin text-emerald-600" /></div>
        ) : transactions.length === 0 ? (
          <div className="text-center py-8 text-gray-400 text-sm">{t('caisse.noTx')}</div>
        ) : (
          <div className="space-y-2">
            {transactions.map(t => (
              <div key={t.id} className="bg-white rounded-xl border border-gray-100 p-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-gray-900">{t.libelle}</div>
                  <div className="text-xs text-gray-400">
                    {MODES_PAIEMENT.find(m => m.code === t.mode_paiement)?.label ?? t.mode_paiement}
                    · {new Date(t.horodatage).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
                <div className={`text-sm font-bold ${t.type === 'entree' ? 'text-green-600' : 'text-red-500'}`}>
                  {t.type === 'entree' ? '+' : '-'}{formatFCFA(t.montant_fcfa)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-gray-900">{t('caisse.newTx')}</h2>
              <button onClick={() => setShowModal(false)}><X size={20} className="text-gray-400" /></button>
            </div>

            <div className="flex gap-2">
              {(['entree', 'sortie'] as const).map(typ => (
                <button key={typ} onClick={() => setForm(f => ({ ...f, type: typ }))}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-semibold capitalize ${
                    form.type === typ
                      ? typ === 'entree' ? 'bg-green-600 text-white' : 'bg-red-500 text-white'
                      : 'bg-gray-100 text-gray-600'
                  }`}
                >{typ === 'entree' ? t('caisse.incomeBtn') : t('caisse.expenseBtn')}</button>
              ))}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('common.amount')} (FCFA)</label>
              <input
                type="number" min={1}
                value={form.montant_fcfa || ''}
                onChange={e => setForm(f => ({ ...f, montant_fcfa: +e.target.value }))}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('caisse.label')}</label>
              <input
                type="text" placeholder="Paiement lettre client Mme Ateba..."
                value={form.libelle}
                onChange={e => setForm(f => ({ ...f, libelle: e.target.value }))}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">{t('caisse.category')}</label>
              <div className="grid grid-cols-2 gap-2">
                {MODES_PAIEMENT.map(m => (
                  <button key={m.code} onClick={() => setForm(f => ({ ...f, mode_paiement: m.code }))}
                    className={`py-2 rounded-lg text-xs font-medium ${
                      form.mode_paiement === m.code ? 'bg-emerald-600 text-white' : 'bg-gray-100 text-gray-600'
                    }`}
                  >{m.label}</button>
                ))}
              </div>
            </div>

            <button
              onClick={() => ajouterMutation.mutate(form)}
              disabled={ajouterMutation.isPending || !form.libelle || !form.montant_fcfa}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 rounded-xl disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {ajouterMutation.isPending && <Loader2 size={16} className="animate-spin" />}
              {t('common.save')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
