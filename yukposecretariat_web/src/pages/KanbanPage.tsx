import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { KanbanSquare, Plus, Loader2, X, Check } from 'lucide-react'
import { gestionAPI } from '../api/client'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { DemoBanner } from '../components/DemoBanner'

type Statut = 'en_attente' | 'en_cours' | 'en_revision' | 'livre' | 'paye' | 'annule'

const COLONNES: { statut: Statut; label: string; color: string }[] = [
  { statut: 'en_attente', label: 'En attente', color: 'border-gray-400' },
  { statut: 'en_cours',   label: 'En cours',   color: 'border-blue-400' },
  { statut: 'en_revision',label: 'Révision',   color: 'border-yellow-400' },
  { statut: 'livre',      label: 'Livré',      color: 'border-purple-400' },
  { statut: 'paye',       label: 'Payé ✓',    color: 'border-green-400' },
]

const STATUT_COLORS: Record<Statut, string> = {
  en_attente: 'bg-gray-100 text-gray-600',
  en_cours: 'bg-blue-100 text-blue-700',
  en_revision: 'bg-yellow-100 text-yellow-700',
  livre: 'bg-purple-100 text-purple-700',
  paye: 'bg-green-100 text-green-700',
  annule: 'bg-red-100 text-red-600',
}

interface BonTravail {
  id: number; client_nom: string; description: string; type_travail: string;
  statut: Statut; montant_fcfa: number; acompte_fcfa: number; reste_a_payer: number; echeance?: string
}

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

export default function KanbanPage() {
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({
    client_nom: '', description: '', type_travail: 'redaction', montant_fcfa: 0, acompte_fcfa: 0
  })

  const { data, isLoading } = useQuery({
    queryKey: ['travaux'],
    queryFn: () => gestionAPI.travaux().then(r => r.data),
  })

  const creerMutation = useMutation({
    mutationFn: (d: typeof form) => gestionAPI.creerTravail(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['travaux'] })
      setShowModal(false)
      setForm({ client_nom: '', description: '', type_travail: 'redaction', montant_fcfa: 0, acompte_fcfa: 0 })
      toast.success('Bon de travail créé')
    },
  })

  const modifierStatut = useMutation({
    mutationFn: ({ id, statut }: { id: number; statut: string }) =>
      gestionAPI.modifierTravail(id, { statut }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['travaux'] }),
  })

  const travaux: BonTravail[] = data?.travaux ?? []

  const parColonne = (statut: Statut) => travaux.filter(t => t.statut === statut)

  const prochainStatut = (statut: Statut): Statut | null => {
    const ordre: Statut[] = ['en_attente', 'en_cours', 'en_revision', 'livre', 'paye']
    const idx = ordre.indexOf(statut)
    return idx >= 0 && idx < ordre.length - 1 ? ordre[idx + 1] : null
  }

  return (
    <div className="space-y-5">
      <DemoBanner />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <KanbanSquare className="text-indigo-600" size={24} />
            File de travaux
          </h1>
          <p className="text-gray-500 text-sm mt-1">{travaux.length} bons de travail</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2.5 rounded-xl text-sm transition-colors"
        >
          <Plus size={18} /> Nouveau
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-600" /></div>
      ) : (
        /* Scroll horizontal sur mobile */
        <div className="overflow-x-auto pb-2">
          <div className="flex gap-4 min-w-max">
            {COLONNES.map(({ statut, label, color }) => {
              const bons = parColonne(statut)
              return (
                <div key={statut} className="w-64 shrink-0">
                  <div className={clsx('border-t-4 rounded-t-lg px-3 py-2 bg-white shadow-sm', color)}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-gray-700">{label}</span>
                      <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{bons.length}</span>
                    </div>
                  </div>
                  <div className="space-y-2 mt-2 min-h-32">
                    {bons.map(b => {
                      const next = prochainStatut(b.statut)
                      return (
                        <div key={b.id} className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
                          <div className="font-semibold text-sm text-gray-900 truncate">{b.client_nom}</div>
                          <div className="text-xs text-gray-400 truncate mt-0.5">{b.description}</div>
                          <div className="flex items-center justify-between mt-2">
                            <span className="text-xs font-semibold text-gray-700">{formatFCFA(b.montant_fcfa)}</span>
                            {b.reste_a_payer > 0 && (
                              <span className="text-xs text-orange-500">Reste: {formatFCFA(b.reste_a_payer)}</span>
                            )}
                          </div>
                          {next && (
                            <button
                              onClick={() => modifierStatut.mutate({ id: b.id, statut: next })}
                              className="mt-2 w-full text-xs py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-600 font-medium flex items-center justify-center gap-1"
                            >
                              <Check size={12} /> Passer à "{next.replace('_', ' ')}"
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Modal création */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-gray-900">Nouveau bon de travail</h2>
              <button onClick={() => setShowModal(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            {[
              { key: 'client_nom', label: 'Nom du client', type: 'text' },
              { key: 'description', label: 'Description du travail', type: 'text' },
              { key: 'montant_fcfa', label: 'Montant (FCFA)', type: 'number' },
              { key: 'acompte_fcfa', label: 'Acompte reçu (FCFA)', type: 'number' },
            ].map(({ key, label, type }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                <input
                  type={type}
                  value={form[key as keyof typeof form]}
                  onChange={e => setForm(f => ({ ...f, [key]: type === 'number' ? +e.target.value : e.target.value }))}
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select
                value={form.type_travail}
                onChange={e => setForm(f => ({ ...f, type_travail: e.target.value }))}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none"
              >
                {['redaction', 'ocr', 'infographie', 'impression', 'saisie', 'autre'].map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <button
              onClick={() => creerMutation.mutate(form)}
              disabled={creerMutation.isPending || !form.client_nom || !form.description}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 rounded-xl disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {creerMutation.isPending && <Loader2 size={16} className="animate-spin" />}
              Créer le bon de travail
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
