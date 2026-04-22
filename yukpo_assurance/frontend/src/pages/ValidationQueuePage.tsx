/**
 * ValidationQueuePage — File de toutes les validations en attente.
 * Vue globale pour les managers et la direction.
 */
import { useEffect, useState } from 'react'
import {
  ShieldCheckIcon as Shield,
  ArrowPathIcon as RefreshCw,
  CheckCircleIcon as CheckCircle,
  XCircleIcon as XCircle,
  ClockIcon as Clock,
  ExclamationTriangleIcon as AlertTriangle,
} from '@heroicons/react/24/outline'
import { useApprovalStore } from '../store/approvalStore'
import { ApprovalCard } from '../components/AgentChat/ApprovalCard'

const API = import.meta.env.VITE_API_URL ?? ''

export default function ValidationQueuePage() {
  const { items, stats, setItems, setStats, chargement, setChargement } = useApprovalStore()
  const [filtre, setFiltre] = useState<'en_attente' | 'approuve' | 'rejete' | 'tous'>('en_attente')

  const charger = async () => {
    setChargement(true)
    try {
      const token = localStorage.getItem('access_token') || ''
      const res = await fetch(`${API}/api/v1/agent/validations?statut=${filtre}&limit=100`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setItems(data.validations ?? [])
        setStats(data.stats ?? stats)
      }
    } finally {
      setChargement(false)
    }
  }

  useEffect(() => { charger() }, [filtre])

  const itemsFiltres = items.filter((i) => filtre === 'tous' || i.statut === filtre)

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* En-tête */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-orange-100 rounded-xl">
          <Shield className="w-6 h-6 text-orange-600" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Validations humaines</h1>
          <p className="text-sm text-gray-500">Décisions en attente — l'agent reprend après validation</p>
        </div>
        <button
          onClick={charger}
          disabled={chargement}
          className="ml-auto p-2 text-gray-500 hover:text-indigo-600 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${chargement ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Statistiques */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <StatCard
          icone={<Clock className="w-5 h-5" />}
          label="En attente"
          valeur={stats.en_attente}
          couleur="orange"
        />
        <StatCard
          icone={<CheckCircle className="w-5 h-5" />}
          label="Approuvés"
          valeur={stats.approuves}
          couleur="green"
        />
        <StatCard
          icone={<XCircle className="w-5 h-5" />}
          label="Rejetés"
          valeur={stats.rejetes}
          couleur="red"
        />
        <StatCard
          icone={<AlertTriangle className="w-5 h-5" />}
          label="Montant en attente"
          valeur={`${(stats.montant_en_attente_fcfa / 1_000_000).toFixed(1)}M`}
          couleur="purple"
          suffix=" FCFA"
        />
      </div>

      {/* Filtres */}
      <div className="flex gap-2 mb-4">
        {(['en_attente', 'approuve', 'rejete', 'tous'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFiltre(s)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
              filtre === s
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {s === 'en_attente' ? 'En attente' :
             s === 'approuve' ? 'Approuvés' :
             s === 'rejete' ? 'Rejetés' : 'Tous'}
          </button>
        ))}
      </div>

      {/* Liste */}
      <div className="space-y-4">
        {chargement && (
          <div className="text-center py-8 text-gray-400">
            <RefreshCw className="w-8 h-8 mx-auto animate-spin mb-2" />
            <p className="text-sm">Chargement...</p>
          </div>
        )}
        {!chargement && itemsFiltres.length === 0 && (
          <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
            <Shield className="w-12 h-12 text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">Aucune validation {filtre === 'en_attente' ? 'en attente' : ''}</p>
          </div>
        )}
        {!chargement && itemsFiltres.map((item) => (
          <ApprovalCard key={item.id} item={item} onRefresh={charger} />
        ))}
      </div>
    </div>
  )
}

function StatCard({
  icone, label, valeur, couleur, suffix = ''
}: {
  icone: React.ReactNode; label: string; valeur: number | string; couleur: string; suffix?: string
}) {
  const colors: Record<string, string> = {
    orange: 'bg-orange-50 text-orange-600',
    green: 'bg-green-50 text-green-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
  }
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className={`inline-flex p-2 rounded-lg ${colors[couleur]} mb-2`}>
        {icone}
      </div>
      <div className="text-xl font-bold text-gray-900">{valeur}{suffix}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  )
}
