/**
 * ApprovalCard — Carte de validation humaine.
 *
 * Affiche les détails d'une action en attente de validation.
 * Boutons Approuver / Rejeter → appelle l'API → l'agent REPREND.
 *
 * Après décision :
 *  - Un indicateur montre que l'agent a repris et le nouveau statut
 *  - Si une nouvelle validation est requise, une nouvelle carte apparaît
 */
import { useState } from 'react'
import {
  ShieldCheckIcon as Shield,
  CheckCircleIcon as CheckCircle,
  XCircleIcon as XCircle,
  ClockIcon as Clock,
  ExclamationTriangleIcon as AlertTriangle,
  ChevronDownIcon as ChevronDown,
  ChevronUpIcon as ChevronUp,
  ArrowPathIcon as RotateCcw,
} from '@heroicons/react/24/outline'
import type { ValidationItem } from '../../store/approvalStore'
import { useApprovalStore } from '../../store/approvalStore'

interface Props {
  item: ValidationItem
  onRefresh: () => void
}

const API = import.meta.env.VITE_API_URL ?? ''

// Labels lisibles par type d'action
const TYPE_LABELS: Record<string, string> = {
  sinistre: 'Décision sinistre',
  emission_police: 'Émission police',
  conge_rh: 'Congé employé',
  recrutement_offre: 'Publication offre emploi',
  embauche: 'Embauche candidat',
  transaction_juridique: 'Transaction amiable',
  ecriture_comptable_grande: 'Écriture comptable > 10M',
  cloture_comptable: 'Clôture comptable',
  rapport_direction: 'Diffusion rapport direction',
}

const NIVEAU_URGENCE = (montant: number) => {
  if (montant >= 5_000_000) return { label: 'Critique', cls: 'bg-red-100 text-red-700' }
  if (montant >= 1_000_000) return { label: 'Important', cls: 'bg-orange-100 text-orange-700' }
  return { label: 'Standard', cls: 'bg-blue-100 text-blue-700' }
}

export function ApprovalCard({ item, onRefresh }: Props) {
  const [commentaire, setCommentaire] = useState('')
  const [motifRejet, setMotifRejet]   = useState('')
  const [showRejet, setShowRejet]     = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [chargement, setChargement]   = useState(false)
  const [reprise, setReprise]         = useState<{ statut: string; resume: string } | null>(null)

  const { mettreAJourItem } = useApprovalStore()
  const urgence = NIVEAU_URGENCE(item.montant)

  const approuver = async () => {
    if (chargement) return
    setChargement(true)
    try {
      const token = localStorage.getItem('access_token') || ''
      const res = await fetch(`${API}/api/v1/agent/approuver/${item.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ commentaire }),
      })
      const data = await res.json()
      mettreAJourItem(item.id, { statut: 'approuve' })

      if (data.reprise) {
        setReprise({ statut: data.reprise.statut, resume: data.reprise.resume })
      }
      onRefresh()
    } catch (err) {
      console.error('[ApprovalCard] Erreur approbation:', err)
    } finally {
      setChargement(false)
    }
  }

  const rejeter = async () => {
    if (!motifRejet.trim() || chargement) return
    setChargement(true)
    try {
      const token = localStorage.getItem('access_token') || ''
      const res = await fetch(`${API}/api/v1/agent/rejeter/${item.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ motif: motifRejet }),
      })
      const data = await res.json()
      mettreAJourItem(item.id, { statut: 'rejete' })

      if (data.reprise) {
        setReprise({ statut: data.reprise.statut, resume: data.reprise.resume })
      }
      onRefresh()
    } catch (err) {
      console.error('[ApprovalCard] Erreur rejet:', err)
    } finally {
      setChargement(false)
    }
  }

  const expiresDans = () => {
    const expires = new Date(item.expires_le)
    const now = new Date()
    const diffH = Math.round((expires.getTime() - now.getTime()) / 3_600_000)
    if (diffH <= 0) return 'Expiré'
    if (diffH === 1) return 'Expire dans 1h'
    return `Expire dans ${diffH}h`
  }

  return (
    <div className="bg-white rounded-xl border-2 border-orange-200 shadow-sm overflow-hidden">
      {/* En-tête */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-orange-50 to-amber-50">
        <Shield className="w-5 h-5 text-orange-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-gray-800">
              {TYPE_LABELS[item.type] || item.type}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${urgence.cls}`}>
              {urgence.label}
            </span>
          </div>
          <p className="text-xs text-gray-500 truncate mt-0.5">{item.description}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-sm font-bold text-gray-900">
            {item.montant > 0 ? `${item.montant.toLocaleString('fr-FR')} FCFA` : '—'}
          </div>
          <div className="flex items-center gap-1 text-xs text-orange-600">
            <Clock className="w-3 h-3" />
            {expiresDans()}
          </div>
        </div>
      </div>

      {/* Détails (dépliables) */}
      <div className="px-4 py-2 border-b border-gray-100">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-indigo-600 transition-colors"
        >
          {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {showDetails ? 'Masquer les détails' : 'Voir les détails'}
        </button>
        {showDetails && (
          <div className="mt-2 bg-gray-50 rounded-lg p-3">
            <pre className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed overflow-x-auto">
              {JSON.stringify(item.donnees, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Après décision : reprise agent */}
      {reprise && (
        <div className={`px-4 py-3 border-b ${
          reprise.statut === 'termine' ? 'bg-green-50 border-green-100' : 'bg-blue-50 border-blue-100'
        }`}>
          <div className="flex items-center gap-2 mb-1">
            <RotateCcw className="w-4 h-4 text-indigo-600" />
            <span className="text-xs font-semibold text-gray-700">Agent a repris le processus</span>
            <span className={`ml-auto text-xs px-2 py-0.5 rounded-full font-medium ${
              reprise.statut === 'termine' ? 'bg-green-100 text-green-700' :
              reprise.statut === 'en_attente_validation' ? 'bg-orange-100 text-orange-700' :
              'bg-blue-100 text-blue-700'
            }`}>
              {reprise.statut === 'termine' ? 'Terminé' :
               reprise.statut === 'en_attente_validation' ? 'Nouvelle validation' : reprise.statut}
            </span>
          </div>
          {reprise.resume && (
            <p className="text-xs text-gray-600 leading-relaxed">{reprise.resume}</p>
          )}
        </div>
      )}

      {/* Zone action (si pas encore traité) */}
      {item.statut === 'en_attente' && !reprise && (
        <div className="px-4 py-3 space-y-3">
          {/* Commentaire optionnel */}
          <input
            type="text"
            placeholder="Commentaire (optionnel)"
            value={commentaire}
            onChange={(e) => setCommentaire(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />

          <div className="flex gap-2">
            <button
              onClick={approuver}
              disabled={chargement}
              className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              <CheckCircle className="w-4 h-4" />
              {chargement ? 'En cours...' : 'Approuver'}
            </button>
            <button
              onClick={() => setShowRejet(!showRejet)}
              disabled={chargement}
              className="flex-1 flex items-center justify-center gap-2 bg-red-50 hover:bg-red-100 text-red-700 text-sm font-semibold py-2 rounded-lg transition-colors border border-red-200"
            >
              <XCircle className="w-4 h-4" />
              Rejeter
            </button>
          </div>

          {showRejet && (
            <div className="space-y-2">
              <textarea
                placeholder="Motif du rejet (obligatoire)..."
                value={motifRejet}
                onChange={(e) => setMotifRejet(e.target.value)}
                rows={2}
                className="w-full text-sm border border-red-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-red-500 resize-none"
              />
              <button
                onClick={rejeter}
                disabled={!motifRejet.trim() || chargement}
                className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold py-2 rounded-lg transition-colors disabled:opacity-50"
              >
                <AlertTriangle className="w-4 h-4" />
                Confirmer le rejet
              </button>
            </div>
          )}

          <p className="text-xs text-gray-400 text-center">
            {item.peut_reprendre
              ? "Après votre décision, l'agent reprendra automatiquement le processus"
              : "Décision enregistrée (reprise manuelle requise)"}
          </p>
        </div>
      )}

      {/* Statut final si déjà traité */}
      {item.statut !== 'en_attente' && !reprise && (
        <div className={`px-4 py-2 flex items-center gap-2 ${
          item.statut === 'approuve' ? 'bg-green-50' : 'bg-red-50'
        }`}>
          {item.statut === 'approuve'
            ? <CheckCircle className="w-4 h-4 text-green-600" />
            : <XCircle className="w-4 h-4 text-red-600" />}
          <span className="text-xs text-gray-600">
            {item.statut === 'approuve' ? 'Approuvé' : 'Rejeté'} par {item.validateur_nom}
            {item.traite_le && ` — ${new Date(item.traite_le).toLocaleString('fr-FR')}`}
          </span>
        </div>
      )}
    </div>
  )
}
