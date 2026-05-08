import { useState, useRef, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard, FileText, Image, KanbanSquare,
  Receipt, Wallet, Users, LogOut, Menu, X, ChevronRight,
  Languages, FolderOpen, CreditCard, Globe, ChevronDown, Shield,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { clsx } from 'clsx'
import { SUPPORTED_LANGUAGES } from '../i18n'

const ADMIN_ROLES = ['admin', 'super_admin', 'yukpo_owner']

const NAV_KEYS = [
  { to: '/dashboard',   key: 'dashboard',   icon: LayoutDashboard, adminOnly: false },
  { to: '/redaction',   key: 'redaction',   icon: FileText,        adminOnly: false },
  { to: '/infographie', key: 'infographie', icon: Image,           adminOnly: false },
  { to: '/traduction',  key: 'traduction',  icon: Languages,       adminOnly: false },
  { to: '/documents',   key: 'documents',   icon: FolderOpen,      adminOnly: false },
  { to: '/kanban',      key: 'kanban',      icon: KanbanSquare,    adminOnly: false },
  { to: '/devis',       key: 'devis',       icon: Receipt,         adminOnly: false },
  { to: '/caisse',      key: 'caisse',      icon: Wallet,          adminOnly: false },
  { to: '/clients',     key: 'clients',     icon: Users,           adminOnly: false },
  { to: '/abonnement',  key: 'abonnement',  icon: CreditCard,      adminOnly: false },
  { to: '/admin',       key: 'admin',       icon: Shield,          adminOnly: true  },
]

function LangMenu() {
  const { i18n, t } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const current = SUPPORTED_LANGUAGES.find(l => l.code === i18n.language)
    ?? SUPPORTED_LANGUAGES.find(l => l.code === i18n.language.split('-')[0])
    ?? SUPPORTED_LANGUAGES[0]

  const change = (code: string) => {
    i18n.changeLanguage(code)
    const dir = SUPPORTED_LANGUAGES.find(l => l.code === code)?.dir || 'ltr'
    document.documentElement.dir = dir
    document.documentElement.lang = code
    setOpen(false)
  }

  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  return (
    <div ref={ref} className="relative px-4 py-2 border-t border-brand-600">
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 text-sm text-brand-200 hover:text-white w-full">
        <Globe size={16} />
        <span className="flex-1 text-left">{current.flag} {current.label}</span>
        <ChevronDown size={13} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute bottom-full left-2 right-2 mb-1 bg-brand-800 border border-brand-600 rounded-lg overflow-hidden shadow-xl z-50">
          {SUPPORTED_LANGUAGES.map(lang => (
            <button key={lang.code} onClick={() => change(lang.code)}
              className={clsx('w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors',
                current.code === lang.code ? 'bg-white/20 text-white' : 'text-brand-200 hover:bg-white/10 hover:text-white')}>
              <span>{lang.flag}</span><span>{lang.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-gray-50">
      {/* Mobile header */}
      <div className="md:hidden flex items-center justify-between bg-brand-700 text-white px-4 py-3 sticky top-0 z-40">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center bg-white rounded-lg"
               style={{ width: 40, height: 40, padding: 1, boxShadow: "0 1px 3px rgba(0,0,0,0.18)" }}>
            <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
          <span className="font-bold text-lg">Yukpo<span className="text-sky-300">Secrétariat</span></span>
        </div>
        <button onClick={() => setOpen(o => !o)} className="p-1">
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Sidebar */}
      <aside className={clsx(
        'fixed md:static inset-y-0 left-0 z-30 w-64 bg-brand-700 text-white flex flex-col transition-transform duration-200',
        open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      )}>
        {/* Logo desktop */}
        <div className="hidden md:flex items-center gap-3 px-5 py-5 border-b border-brand-600">
          <div className="flex items-center justify-center bg-white rounded-xl flex-shrink-0"
               style={{ width: 56, height: 56, padding: 2, boxShadow: "0 1px 3px rgba(0,0,0,0.18)" }}>
            <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-lg font-bold tracking-tight">Yukpo<span className="text-sky-300">Secrétariat</span></span>
            <span className="text-[10px] tracking-wide text-brand-300">Back-office professionnel</span>
          </div>
        </div>

        {/* User pill */}
        <div className="px-4 py-3 border-b border-brand-600 text-sm">
          <div className="font-semibold">{user?.user_nom || 'Utilisateur'}</div>
          <div className="text-brand-300 text-xs capitalize">{user?.role || 'agent'}</div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 space-y-0.5">
          {NAV_KEYS.filter(item => !item.adminOnly || ADMIN_ROLES.includes(user?.role || '')).map(({ to, key, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg mx-2 transition-colors',
                isActive ? 'bg-white/15 text-white' : 'text-brand-200 hover:bg-white/10 hover:text-white',
              )}
            >
              <Icon size={18} />
              <span>{t(`nav.${key}`)}</span>
              <ChevronRight size={14} className="ml-auto opacity-40" />
            </NavLink>
          ))}
        </nav>

        {/* Language switcher */}
        <LangMenu />

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-3 text-sm text-brand-300 hover:text-white hover:bg-white/10 border-t border-brand-600 transition-colors"
        >
          <LogOut size={18} />
          {t('nav.logout')}
        </button>
      </aside>

      {/* Overlay mobile */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-20 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
