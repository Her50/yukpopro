import { useQuery } from '@tanstack/react-query'
import { FileText, Scan, Mic, FolderOpen, Image, KanbanSquare, Wallet, ArrowRight, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { gestionAPI } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { DemoBanner } from '../components/DemoBanner'

const ACCES_RAPIDES = [
  { label: 'Créer une infographie', icon: Image, to: '/infographie', color: 'bg-orange-500', desc: 'Flyers, cartes, affiches' },
  { label: 'Gérer les travaux', icon: KanbanSquare, to: '/kanban', color: 'bg-indigo-500', desc: 'File Kanban' },
  { label: 'Caisse du jour', icon: Wallet, to: '/caisse', color: 'bg-emerald-500', desc: 'Enregistrer une recette' },
]

const REDACTION_MODES = [
  { tab: 'texte', label: 'Texte',     icon: FileText,   color: 'bg-blue-500',   desc: '30+ types de documents IA' },
  { tab: 'scan',  label: 'Scan',      icon: Scan,       color: 'bg-green-500',  desc: 'Image / papier → Word' },
  { tab: 'audio', label: 'Audio',     icon: Mic,        color: 'bg-purple-500', desc: 'Dictée / audio → Word' },
  { tab: 'doc',   label: 'Document',  icon: FolderOpen, color: 'bg-amber-500',  desc: 'Améliorer un brouillon' },
] as const

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

/**
 * Retourne le prénom à afficher dans la salutation.
 * Priorité : prenoms du DB → nom (1er mot) → user_nom (1er mot, sans @ si email).
 */
function prenomAffichage(user: { prenoms?: string | null; nom?: string | null; user_nom?: string } | null): string {
  if (!user) return ''
  if (user.prenoms && user.prenoms.trim()) {
    return user.prenoms.trim().split(' ')[0]
  }
  const candidats = [user.nom, user.user_nom].filter((s): s is string => !!s && s.trim().length > 0)
  for (const c of candidats) {
    const propre = c.includes('@')
      ? c.split('@')[0].replace(/[._]/g, ' ').trim()
      : c.trim()
    if (propre) {
      return propre.split(' ')[0].charAt(0).toUpperCase() + propre.split(' ')[0].slice(1)
    }
  }
  return ''
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()

  const { data: caisse } = useQuery({
    queryKey: ['caisse-today'],
    queryFn: async () => {
      const r = await gestionAPI.transactions()
      return r.data
    },
  })

  const { data: travaux } = useQuery({
    queryKey: ['travaux'],
    queryFn: async () => {
      const r = await gestionAPI.travaux()
      return r.data
    },
  })

  const totalJour = caisse?.rapport?.total_entrees ?? 0
  const enAttente = travaux?.travaux?.filter((t: { statut: string }) => t.statut === 'en_attente').length ?? 0
  const enCours = travaux?.travaux?.filter((t: { statut: string }) => t.statut === 'en_cours').length ?? 0

  return (
    <div className="space-y-6">
      <DemoBanner />
      {/* Greeting */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Bonjour, {prenomAffichage(user) || 'secrétaire'} 👋
        </h1>
        <p className="text-gray-500 text-sm mt-1">Que souhaitez-vous faire aujourd'hui ?</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 col-span-2 sm:col-span-1">
          <div className="text-xs text-gray-500 mb-1">Caisse du jour</div>
          <div className="text-base sm:text-lg font-bold text-emerald-600 truncate">{formatFCFA(totalJour)}</div>
        </div>
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
          <div className="text-xs text-gray-500 mb-1">En attente</div>
          <div className="text-base sm:text-lg font-bold text-orange-500">{enAttente}</div>
        </div>
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
          <div className="text-xs text-gray-500 mb-1">En cours</div>
          <div className="text-base sm:text-lg font-bold text-blue-600">{enCours}</div>
        </div>
      </div>

      {/* Rédaction Yukpo — hub principal */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-700 flex items-center gap-2">
            <Sparkles size={16} className="text-brand-600" />
            Rédaction Yukpo
          </h2>
          <button onClick={() => navigate('/redaction')}
            className="text-xs text-brand-600 hover:text-brand-700 font-medium flex items-center gap-1">
            Ouvrir le hub <ArrowRight size={12} />
          </button>
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Tous les modes de production de documents en un seul endroit. Vous pouvez chaîner :
          un scan ou un audio peut être renvoyé vers le mode Texte pour être reformulé / converti.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {REDACTION_MODES.map(({ tab, label, icon: Icon, color, desc }) => (
            <button
              key={tab}
              onClick={() => navigate(`/redaction?tab=${tab}`)}
              className="flex flex-col items-start gap-2 bg-white rounded-2xl p-4 shadow-sm border border-gray-100 hover:shadow-md hover:border-brand-200 transition-all text-left"
            >
              <div className={`${color} text-white rounded-xl p-2.5`}>
                <Icon size={18} />
              </div>
              <div>
                <div className="font-semibold text-sm text-gray-900">{label}</div>
                <div className="text-xs text-gray-400 mt-0.5">{desc}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Autres accès rapides */}
      <div>
        <h2 className="text-base font-semibold text-gray-700 mb-3">Accès rapides</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {ACCES_RAPIDES.map(({ label, icon: Icon, to, color, desc }) => (
            <button
              key={to}
              onClick={() => navigate(to)}
              className="flex items-center gap-4 bg-white rounded-2xl p-4 shadow-sm border border-gray-100 hover:shadow-md hover:border-brand-200 transition-all text-left"
            >
              <div className={`${color} text-white rounded-xl p-3 shrink-0`}>
                <Icon size={22} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm text-gray-900">{label}</div>
                <div className="text-xs text-gray-400 truncate">{desc}</div>
              </div>
              <ArrowRight size={16} className="text-gray-300 shrink-0" />
            </button>
          ))}
        </div>
      </div>

      {/* Derniers travaux */}
      {travaux?.travaux?.length > 0 && (
        <div>
          <h2 className="text-base font-semibold text-gray-700 mb-3">Derniers travaux</h2>
          <div className="space-y-2">
            {travaux.travaux.slice(0, 5).map((t: {
              id: number; client_nom: string; description: string;
              statut: string; montant_fcfa: number
            }) => (
              <div key={t.id} className="bg-white rounded-xl p-3 border border-gray-100 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-sm text-gray-900 truncate">{t.client_nom}</div>
                  <div className="text-xs text-gray-400 truncate">{t.description}</div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xs font-semibold text-gray-700">{formatFCFA(t.montant_fcfa)}</div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    t.statut === 'paye' ? 'bg-green-100 text-green-700' :
                    t.statut === 'en_cours' ? 'bg-blue-100 text-blue-700' :
                    t.statut === 'livre' ? 'bg-purple-100 text-purple-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>{t.statut.replace('_', ' ')}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
