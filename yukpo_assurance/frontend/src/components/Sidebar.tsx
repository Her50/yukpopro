/**
 * Sidebar Yukpo — Navigation agent-first.
 *
 * Architecture :
 *  - Agents IA = point d'entrée principal pour toutes les actions
 *  - Modules = vues lecture/historique uniquement (non redondantes avec les agents)
 *  - Administration = paramètres
 */
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  HomeIcon,
  ChatBubbleLeftRightIcon,
  ShieldExclamationIcon,
  DocumentTextIcon,
  ScaleIcon,
  XMarkIcon,
  BanknotesIcon,
  ShieldCheckIcon,
  Cog6ToothIcon,
  SparklesIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CpuChipIcon,
  ArrowRightCircleIcon,
  FolderOpenIcon,
} from '@heroicons/react/24/outline'
import { useCompagnieStore } from '../store/compagnieStore'
import { useApprovalStore } from '../store/approvalStore'
import { useState } from 'react'

// ─── Navigation primaire (actions → agents) ───────────────────────────────────
const NAV_PRIMAIRE = [
  { path: '/dashboard',   label: 'Tableau de bord',  icon: HomeIcon },
  { path: '/agents',      label: 'Agents IA',         icon: CpuChipIcon,            badge: 'NOUVEAU' },
  { path: '/validations', label: 'Validations',       icon: ShieldCheckIcon },
  { path: '/chat',        label: 'Yukpo IA Copilote', icon: ChatBubbleLeftRightIcon },
]

// ─── Modules consultation (lecture / historique) ──────────────────────────────
const NAV_MODULES = [
  { path: '/sinistres',    label: 'Sinistres',              icon: ShieldExclamationIcon },
  { path: '/souscription', label: 'Polices & Souscription', icon: DocumentTextIcon },
  { path: '/comptabilite', label: 'Comptabilité',           icon: BanknotesIcon },
  { path: '/reassurance',  label: 'Réassurance',            icon: ArrowRightCircleIcon },
  { path: '/cima',         label: 'Conformité CIMA',        icon: ScaleIcon },
  { path: '/documents',    label: 'Documents générés',      icon: FolderOpenIcon },
  { path: '/fournisseurs', label: 'Prestataires',           icon: HomeIcon },
]

// ─── Administration ───────────────────────────────────────────────────────────
const NAV_ADMIN = [
  { path: '/parametres',   label: 'Paramètres',        icon: Cog6ToothIcon },
]

// Raccourcis agents populaires (suggestions rapides)
const RACCOURCIS_AGENTS = [
  { emoji: '🚗', label: 'Nouveau sinistre',    instruction: 'Instruis un nouveau sinistre auto' },
  { emoji: '📋', label: 'Nouvelle police',     instruction: 'Émet une nouvelle police RC auto' },
  { emoji: '🫀', label: 'Contrat vie',         instruction: 'Souscris un contrat épargne vie' },
  { emoji: '📊', label: 'Ratios CIMA',         instruction: 'Calcule les ratios prudentiels du trimestre' },
  { emoji: '🧮', label: 'Provisions CIMA',     instruction: 'Calcule toutes les provisions techniques CIMA de l\'exercice' },
  { emoji: '📑', label: 'États CIMA',          instruction: 'Génère la liasse complète états C1-C12 et contrôle la cohérence' },
  { emoji: '🔬', label: 'Schéma SI',           instruction: 'Introspecte le schéma ORASS et cartographie les tables métier' },
  { emoji: '🏭', label: 'Créer un agent',      instruction: 'Analyse la couverture des agents et détecte les workflows SI non couverts pour générer de nouveaux agents' },
]

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const location    = useLocation()
  const navigate    = useNavigate()
  const { branding } = useCompagnieStore()
  const { stats }   = useApprovalStore()
  const [modulesOpen, setModulesOpen] = useState(false)
  const [raccourcisOpen, setRaccourcisOpen] = useState(false)

  const navLinkClass = ({ isActive }: { isActive: boolean }, path: string) =>
    clsx(
      'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all',
      isActive || (location.pathname.startsWith(path) && path !== '/')
        ? 'text-white shadow-sm'
        : 'text-gray-300 hover:bg-white/10 hover:text-white'
    )

  const handleRaccourci = (instruction: string) => {
    // Naviguer vers agents et pré-remplir l'instruction via query param
    navigate(`/agents?instruction=${encodeURIComponent(instruction)}`)
    if (window.innerWidth < 1024) onClose()
  }

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-20 bg-black/50 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={clsx(
          'fixed left-0 top-0 z-30 h-full w-64 flex flex-col transition-transform duration-300 lg:translate-x-0 lg:static lg:z-auto',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        style={{ background: 'linear-gradient(180deg, #1e2640 0%, #162033 100%)' }}
      >
        {/* ── Logo Yukpo ── */}
        <div
          className="flex items-center justify-between h-16 px-4 border-b"
          style={{ borderColor: 'rgba(255,255,255,0.08)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg overflow-hidden"
              style={{ background: 'linear-gradient(135deg, #00B0F0, #0054A6)' }}
            >
              {branding.logo_url ? (
                <img src={branding.logo_url} alt={branding.nom} className="w-full h-full object-contain" />
              ) : (
                <span className="text-white font-black text-lg">Y</span>
              )}
            </div>
            <div className="min-w-0">
              <span className="text-white font-black text-base block truncate tracking-tight">
                {branding.nom || 'Yukpo'}
              </span>
              <p className="text-xs truncate" style={{ color: 'rgba(186,230,253,0.6)' }}>
                {branding.slogan || 'Assurance · Zone CIMA'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="lg:hidden text-gray-400 hover:text-white transition-colors ml-2 flex-shrink-0">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* ── Navigation principale ── */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">

          {/* Nav primaire */}
          {NAV_PRIMAIRE.map(({ path, label, icon: Icon, badge }: any) => (
            <NavLink
              key={path}
              to={path}
              onClick={() => { if (window.innerWidth < 1024) onClose() }}
              className={(state) => navLinkClass(state, path)}
              style={({ isActive }) => isActive || location.pathname.startsWith(path)
                ? { background: 'linear-gradient(135deg, #0054A6, #003476)' }
                : {}}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              <span className="flex-1 truncate">{label}</span>
              {badge && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded-full font-bold flex-shrink-0"
                  style={{ background: 'rgba(0,176,240,0.3)', color: '#7dd3fc', border: '1px solid rgba(0,176,240,0.4)' }}
                >
                  {badge}
                </span>
              )}
              {path === '/validations' && stats.en_attente > 0 && (
                <span className="flex-shrink-0 bg-orange-500 text-white text-xs w-5 h-5 rounded-full flex items-center justify-center font-bold">
                  {stats.en_attente}
                </span>
              )}
            </NavLink>
          ))}

          {/* ── Raccourcis Agents ── */}
          <div className="mt-4">
            <button
              onClick={() => setRaccourcisOpen(!raccourcisOpen)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-colors"
              style={{ color: 'rgba(186,230,253,0.5)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'rgba(186,230,253,0.8)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(186,230,253,0.5)')}
            >
              <SparklesIcon className="h-3.5 w-3.5" />
              <span>Raccourcis agents</span>
              {raccourcisOpen
                ? <ChevronDownIcon className="h-3 w-3 ml-auto" />
                : <ChevronRightIcon className="h-3 w-3 ml-auto" />}
            </button>

            {raccourcisOpen && (
              <div className="mt-1 space-y-1">
                {RACCOURCIS_AGENTS.map((r) => (
                  <button
                    key={r.label}
                    onClick={() => handleRaccourci(r.instruction)}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all text-gray-400 hover:text-white hover:bg-white/8"
                    style={{ fontSize: '12px' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <span className="text-base">{r.emoji}</span>
                    <span className="font-medium truncate">{r.label}</span>
                  </button>
                ))}
                <NavLink
                  to="/agents"
                  onClick={() => { if (window.innerWidth < 1024) onClose() }}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors"
                  style={{ color: '#00B0F0' }}
                >
                  <CpuChipIcon className="h-3.5 w-3.5" />
                  Voir tous les agents →
                </NavLink>
              </div>
            )}
          </div>

          {/* ── Modules consultation ── */}
          <div className="mt-4">
            <button
              onClick={() => setModulesOpen(!modulesOpen)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-colors"
              style={{ color: 'rgba(186,230,253,0.5)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'rgba(186,230,253,0.8)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(186,230,253,0.5)')}
            >
              <span className="flex-1 text-left">Modules</span>
              {modulesOpen
                ? <ChevronDownIcon className="h-3 w-3" />
                : <ChevronRightIcon className="h-3 w-3" />}
            </button>

            {modulesOpen && (
              <div className="mt-1 space-y-0.5">
                {NAV_MODULES.map(({ path, label, icon: Icon }) => (
                  <NavLink
                    key={path}
                    to={path}
                    onClick={() => { if (window.innerWidth < 1024) onClose() }}
                    className={(state) => clsx(
                      'flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all',
                      state.isActive || location.pathname.startsWith(path)
                        ? 'bg-white/10 text-white'
                        : 'text-gray-400 hover:bg-white/6 hover:text-gray-200'
                    )}
                    onMouseEnter={(e) => { if (!e.currentTarget.classList.contains('bg-white/10')) e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
                    onMouseLeave={(e) => { if (!e.currentTarget.classList.contains('bg-white/10')) e.currentTarget.style.background = 'transparent' }}
                  >
                    <Icon className="h-4 w-4 flex-shrink-0" />
                    <span className="truncate">{label}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        </nav>

        {/* ── Administration ── */}
        <div
          className="px-3 pb-2 space-y-0.5 pt-2"
          style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}
        >
          {NAV_ADMIN.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              onClick={() => { if (window.innerWidth < 1024) onClose() }}
              className={(state) => clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all',
                state.isActive ? 'bg-white/10 text-white' : 'text-gray-300 hover:bg-white/10 hover:text-white'
              )}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </div>

        {/* ── Footer statut ── */}
        <div className="p-4" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              <span className="text-xs" style={{ color: 'rgba(186,230,253,0.5)' }}>API connectée</span>
            </div>
            <span className="text-xs" style={{ color: 'rgba(186,230,253,0.3)' }}>v2.0</span>
          </div>
        </div>
      </aside>
    </>
  )
}
