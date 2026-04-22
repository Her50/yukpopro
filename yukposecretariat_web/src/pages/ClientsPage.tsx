import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, Plus, Search, Phone, X, Loader2, MessageCircle } from 'lucide-react'
import { gestionAPI } from '../api/client'
import toast from 'react-hot-toast'

interface Client {
  id: number; nom: string; telephone: string; email?: string;
  nb_commandes: number; total_paye_fcfa: number; derniere_visite?: string
}

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

export default function ClientsPage() {
  const qc = useQueryClient()
  const [recherche, setRecherche] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ nom: '', telephone: '', email: '', adresse: '', notes: '' })
  const [whatsappMsg, setWhatsappMsg] = useState('Bonjour, votre document est prêt.')

  const { data, isLoading } = useQuery({
    queryKey: ['clients', recherche],
    queryFn: () => gestionAPI.clients(recherche || undefined).then(r => r.data),
    staleTime: 30_000,
  })

  const creerMutation = useMutation({
    mutationFn: (d: typeof form) => gestionAPI.creerClient(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      setShowModal(false)
      setForm({ nom: '', telephone: '', email: '', adresse: '', notes: '' })
      toast.success('Client créé')
    },
    onError: () => toast.error('Erreur'),
  })

  const ouvrirWhatsapp = async (clientId: number) => {
    try {
      const r = await gestionAPI.whatsappClient(clientId, whatsappMsg)
      window.open(r.data.whatsapp_url, '_blank')
    } catch {
      toast.error('Erreur')
    }
  }

  const clients: Client[] = data?.clients ?? []

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Users className="text-violet-600" size={24} />
            Clients
          </h1>
          <p className="text-gray-500 text-sm mt-1">{data?.total ?? 0} clients enregistrés</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-violet-600 hover:bg-violet-700 text-white font-semibold px-4 py-2.5 rounded-xl text-sm"
        >
          <Plus size={18} /> Nouveau
        </button>
      </div>

      {/* Recherche */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Rechercher par nom ou téléphone…"
          value={recherche}
          onChange={e => setRecherche(e.target.value)}
          className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
        />
      </div>

      {/* Message WhatsApp par défaut */}
      <div className="bg-green-50 border border-green-200 rounded-xl p-3">
        <label className="text-xs font-semibold text-green-700 mb-1 block">Message WhatsApp par défaut</label>
        <input
          type="text"
          value={whatsappMsg}
          onChange={e => setWhatsappMsg(e.target.value)}
          className="w-full bg-white border border-green-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
        />
      </div>

      {/* Liste */}
      {isLoading ? (
        <div className="flex justify-center py-10"><Loader2 size={22} className="animate-spin text-violet-600" /></div>
      ) : clients.length === 0 ? (
        <div className="text-center py-10 text-gray-400 text-sm">
          {recherche ? 'Aucun client trouvé' : 'Aucun client enregistré'}
        </div>
      ) : (
        <div className="space-y-2">
          {clients.map(c => (
            <div key={c.id} className="bg-white rounded-xl border border-gray-100 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-gray-900">{c.nom}</div>
                  <div className="flex items-center gap-1 text-sm text-gray-500 mt-0.5">
                    <Phone size={12} /> {c.telephone}
                  </div>
                  {c.email && <div className="text-xs text-gray-400 mt-0.5">{c.email}</div>}
                </div>
                <button
                  onClick={() => ouvrirWhatsapp(c.id)}
                  className="flex items-center gap-1.5 bg-green-500 hover:bg-green-600 text-white text-xs font-medium px-3 py-2 rounded-xl shrink-0 transition-colors"
                >
                  <MessageCircle size={14} /> WhatsApp
                </button>
              </div>
              <div className="flex gap-4 mt-3 text-xs text-gray-400">
                <span>{c.nb_commandes} commandes</span>
                <span>Total payé : {formatFCFA(c.total_paye_fcfa)}</span>
                {c.derniere_visite && (
                  <span>Dernière visite : {new Date(c.derniere_visite).toLocaleDateString('fr-FR')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal création */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end md:items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-bold text-gray-900">Nouveau client</h2>
              <button onClick={() => setShowModal(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            {[
              { key: 'nom', label: 'Nom complet *', type: 'text' },
              { key: 'telephone', label: 'Téléphone *', type: 'tel' },
              { key: 'email', label: 'Email (optionnel)', type: 'email' },
              { key: 'adresse', label: 'Adresse / quartier', type: 'text' },
            ].map(({ key, label, type }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                <input
                  type={type}
                  value={form[key as keyof typeof form]}
                  onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
              </div>
            ))}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
              <textarea
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                rows={2}
                placeholder="Préférences, besoins habituels..."
                className="w-full border border-gray-300 rounded-xl px-4 py-2 text-sm focus:outline-none resize-none"
              />
            </div>
            <button
              onClick={() => creerMutation.mutate(form)}
              disabled={creerMutation.isPending || !form.nom || !form.telephone}
              className="w-full bg-violet-600 hover:bg-violet-700 text-white font-semibold py-3 rounded-xl disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {creerMutation.isPending && <Loader2 size={16} className="animate-spin" />}
              Créer le client
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
