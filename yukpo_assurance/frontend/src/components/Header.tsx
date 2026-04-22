import { Fragment } from 'react'
import { Menu, Transition } from '@headlessui/react'
import {
  Bars3Icon, BellIcon, ChevronDownIcon,
  UserCircleIcon, ArrowRightOnRectangleIcon, Cog6ToothIcon,
  ShieldCheckIcon, CpuChipIcon,
} from '@heroicons/react/24/outline'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { useCompagnieStore } from '../store/compagnieStore'
import { useApprovalStore } from '../store/approvalStore'
import { clsx } from 'clsx'

interface HeaderProps {
  onMenuClick: () => void
  title?: string
}

export function Header({ onMenuClick, title }: HeaderProps) {
  const { user, logout }  = useAuth()
  const { branding }      = useCompagnieStore()
  const { stats }         = useApprovalStore()
  const navigate          = useNavigate()

  return (
    <header
      className="h-14 flex items-center justify-between px-4 lg:px-6 z-10 flex-shrink-0"
      style={{
        background: 'linear-gradient(90deg, #0054A6 0%, #003476 50%, #1e2640 100%)',
        borderBottom: '1px solid rgba(0,176,240,0.2)',
        boxShadow: '0 1px 12px rgba(0,0,0,0.25)',
      }}
    >
      {/* ── Gauche ── */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-lg text-blue-200 hover:bg-white/10 transition-colors flex-shrink-0"
        >
          <Bars3Icon className="h-5 w-5" />
        </button>

        {/* Breadcrumb titre */}
        {title && (
          <div className="hidden sm:flex items-center gap-2">
            <span className="text-blue-300/60 text-xs">Yukpo</span>
            <span className="text-blue-300/40 text-xs">/</span>
            <span className="text-white text-sm font-semibold tracking-tight truncate max-w-xs">{title}</span>
          </div>
        )}
      </div>

      {/* ── Centre — raccourci Agents ── */}
      <button
        onClick={() => navigate('/agents')}
        className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all group"
        style={{ background: 'rgba(0,176,240,0.12)', border: '1px solid rgba(0,176,240,0.25)' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(0,176,240,0.22)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(0,176,240,0.12)')}
      >
        <CpuChipIcon className="h-4 w-4 text-blue-300" />
        <span className="text-blue-100 text-xs font-semibold">Yukpo Agents IA</span>
        <span
          className="text-xs px-1.5 py-0.5 rounded-full font-bold"
          style={{ background: 'rgba(0,176,240,0.3)', color: '#7dd3fc' }}
        >
          15 agents
        </span>
      </button>

      {/* ── Droite ── */}
      <div className="flex items-center gap-2">

        {/* Badge pays */}
        <span
          className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
          style={{ background: 'rgba(255,255,255,0.1)', color: 'rgba(186,230,253,0.8)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block animate-pulse" />
          {branding.pays} · {branding.devise}
        </span>

        {/* Validations badge */}
        {stats.en_attente > 0 && (
          <button
            onClick={() => navigate('/validations')}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all"
            style={{ background: 'rgba(249,115,22,0.2)', border: '1px solid rgba(249,115,22,0.4)' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(249,115,22,0.3)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(249,115,22,0.2)')}
          >
            <ShieldCheckIcon className="h-4 w-4 text-orange-300 animate-pulse" />
            <span className="text-orange-200 text-xs font-bold">{stats.en_attente}</span>
          </button>
        )}

        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-blue-200 hover:bg-white/10 transition-colors">
          <BellIcon className="h-5 w-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-orange-400 rounded-full" />
        </button>

        {/* User menu */}
        <Menu as="div" className="relative">
          <Menu.Button className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/10 transition-colors">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center shadow-inner"
              style={{ background: 'linear-gradient(135deg, #00B0F0, #0054A6)' }}
            >
              <span className="text-white text-xs font-black">
                {user?.prenom?.[0] || user?.email?.[0]?.toUpperCase() || 'U'}
              </span>
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-white text-xs font-semibold leading-tight">
                {user ? `${user.prenom} ${user.nom}` : 'Utilisateur'}
              </p>
              <p className="text-blue-300 text-xs opacity-70">{user?.role || 'Collaborateur'}</p>
            </div>
            <ChevronDownIcon className="h-3.5 w-3.5 text-blue-300" />
          </Menu.Button>

          <Transition
            as={Fragment}
            enter="transition ease-out duration-100"
            enterFrom="transform opacity-0 scale-95"
            enterTo="transform opacity-100 scale-100"
            leave="transition ease-in duration-75"
            leaveFrom="transform opacity-100 scale-100"
            leaveTo="transform opacity-0 scale-95"
          >
            <Menu.Items className="absolute right-0 mt-2 w-52 bg-white rounded-xl shadow-xl border border-gray-100 py-1.5 focus:outline-none overflow-hidden">
              <div className="px-4 py-2 border-b border-gray-50">
                <p className="text-sm font-bold text-gray-800">
                  {user ? `${user.prenom} ${user.nom}` : 'Utilisateur'}
                </p>
                <p className="text-xs text-gray-400">{user?.email || ''}</p>
              </div>
              {[
                { icon: UserCircleIcon,  label: 'Mon profil',          action: () => {} },
                { icon: Cog6ToothIcon,   label: 'Paramètres compagnie', action: () => navigate('/parametres') },
              ].map(({ icon: Icon, label, action }) => (
                <Menu.Item key={label}>
                  {({ active }) => (
                    <button
                      onClick={action}
                      className={clsx(
                        'flex w-full items-center gap-2.5 px-4 py-2 text-sm transition-colors',
                        active ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                      )}
                    >
                      <Icon className="h-4 w-4 opacity-60" />
                      {label}
                    </button>
                  )}
                </Menu.Item>
              ))}
              <div className="my-1 border-t border-gray-100" />
              <Menu.Item>
                {({ active }) => (
                  <button
                    onClick={logout}
                    className={clsx(
                      'flex w-full items-center gap-2.5 px-4 py-2 text-sm transition-colors',
                      active ? 'bg-red-50 text-red-700' : 'text-red-500'
                    )}
                  >
                    <ArrowRightOnRectangleIcon className="h-4 w-4" />
                    Déconnexion
                  </button>
                )}
              </Menu.Item>
            </Menu.Items>
          </Transition>
        </Menu>
      </div>
    </header>
  )
}
