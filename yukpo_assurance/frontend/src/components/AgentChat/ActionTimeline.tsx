/**
 * ActionTimeline — Affiche les étapes de l'agent en temps réel.
 * Chaque étape est une action outil, un appel IA, ou un résultat.
 */
import {
  CheckCircleIcon as CheckCircle,
  ClockIcon as Clock,
  XCircleIcon as XCircle,
  BoltIcon as Zap,
  CpuChipIcon as Bot,
  ExclamationCircleIcon as AlertCircle,
  ShieldCheckIcon as Shield,
  QuestionMarkCircleIcon as Question,
} from '@heroicons/react/24/outline'
import type { EtapeAgent } from '../../store/agentStore'

interface Props {
  etapes: EtapeAgent[]
  enCours: boolean
}

export function ActionTimeline({ etapes, enCours }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 bg-gray-50 border-b border-gray-100">
        <Zap className="w-4 h-4 text-indigo-600" />
        <span className="text-sm font-semibold text-gray-700">Journal d'exécution</span>
        <span className="ml-auto text-xs text-gray-400">{etapes.length} étape(s)</span>
      </div>

      <div className="divide-y divide-gray-50">
        {etapes.map((etape, idx) => (
          <EtapeItem key={etape.id || idx} etape={etape} />
        ))}

        {enCours && (
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="w-6 h-6 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin flex-shrink-0" />
            <span className="text-sm text-indigo-600 font-medium animate-pulse">Agent en cours...</span>
          </div>
        )}
      </div>
    </div>
  )
}

function EtapeItem({ etape }: { etape: EtapeAgent }) {
  const { icone, couleur, bgCouleur } = getStyleEtape(etape)

  return (
    <div className={`flex items-start gap-3 px-4 py-3 ${bgCouleur} transition-colors`}>
      <div className={`mt-0.5 flex-shrink-0 ${couleur}`}>
        {icone}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-800 truncate">{etape.libelle}</span>
          {etape.duree_ms > 0 && (
            <span className="text-xs text-gray-400 flex-shrink-0">
              {etape.duree_ms < 1000 ? `${etape.duree_ms}ms` : `${(etape.duree_ms/1000).toFixed(1)}s`}
            </span>
          )}
        </div>
        {etape.detail && (
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-2 leading-relaxed">
            {etape.detail}
          </p>
        )}
        {etape.type === 'validation' && !!etape.donnees?.validation_id && (
          <div className="mt-1.5 inline-flex items-center gap-1 bg-orange-100 text-orange-700 text-xs px-2 py-0.5 rounded-full font-medium">
            <Shield className="w-3 h-3" />
            ID: {String(etape.donnees?.validation_id ?? '').slice(0, 8)}…
          </div>
        )}
        {etape.type === 'question' && !!etape.donnees?.question_id && (
          <div className="mt-1.5 inline-flex items-center gap-1 bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full font-medium">
            <Question className="w-3 h-3" />
            En attente de votre réponse
          </div>
        )}
      </div>
      <div className="flex-shrink-0 text-xs text-gray-400">
        {new Date(etape.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </div>
    </div>
  )
}

function getStyleEtape(etape: EtapeAgent) {
  if (etape.statut === 'erreur') {
    return { icone: <XCircle className="w-4 h-4" />, couleur: 'text-red-500', bgCouleur: 'bg-red-50' }
  }
  if (etape.type === 'question') {
    return { icone: <Question className="w-4 h-4" />, couleur: 'text-blue-600', bgCouleur: 'bg-blue-50' }
  }
  if (etape.type === 'validation') {
    return { icone: <Shield className="w-4 h-4" />, couleur: 'text-orange-500', bgCouleur: 'bg-orange-50' }
  }
  if (etape.type === 'ia') {
    return { icone: <Bot className="w-4 h-4" />, couleur: 'text-purple-500', bgCouleur: '' }
  }
  if (etape.type === 'resultat') {
    return { icone: <CheckCircle className="w-4 h-4" />, couleur: 'text-green-500', bgCouleur: 'bg-green-50' }
  }
  if (etape.statut === 'en_cours') {
    return { icone: <Clock className="w-4 h-4 animate-pulse" />, couleur: 'text-indigo-500', bgCouleur: '' }
  }
  if (etape.statut === 'ok') {
    return { icone: <CheckCircle className="w-4 h-4" />, couleur: 'text-indigo-500', bgCouleur: '' }
  }
  return { icone: <AlertCircle className="w-4 h-4" />, couleur: 'text-gray-400', bgCouleur: '' }
}
