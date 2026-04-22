import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, FileText, Scan, Mic, Image, KanbanSquare,
  Receipt, Wallet, Users, LogOut, Menu, X, ChevronRight,
  Languages, FolderOpen,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { clsx } from 'clsx'

const NAV = [
  { to: '/dashboard',   label: 'Tableau de bord', icon: LayoutDashboard },
  { to: '/redaction',   label: 'Rédaction IA',    icon: FileText },
  { to: '/ocr',         label: 'Scan → Texte',    icon: Scan },
  { to: '/audio',       label: 'Audio → Doc',     icon: Mic },
  { to: '/infographie', label: 'Infographie',      icon: Image },
  { to: '/traduction',  label: 'Traduction IA',    icon: Languages },
  { to: '/documents',   label: 'Mes Documents',    icon: FolderOpen },
  { to: '/kanban',      label: 'File de travaux',  icon: KanbanSquare },
  { to: '/devis',       label: 'Devis & Factures', icon: Receipt },
  { to: '/caisse',      label: 'Caisse',           icon: Wallet },
  { to: '/clients',     label: 'Clients',          icon: Users },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-gray-50">
      {/* Mobile header */}
      <div className="md:hidden flex items-center justify-between bg-brand-700 text-white px-4 py-3 sticky top-0 z-40">
        <span className="font-bold text-lg">YukpoSecrétariat</span>
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
        <div className="hidden md:flex items-center gap-2 px-5 py-5 border-b border-brand-600">
          <span className="text-xl font-bold">YukpoSecrétariat</span>
        </div>

        {/* User pill */}
        <div className="px-4 py-3 border-b border-brand-600 text-sm">
          <div className="font-semibold">{user?.user_nom || 'Utilisateur'}</div>
          <div className="text-brand-300 text-xs capitalize">{user?.role || 'agent'}</div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 space-y-0.5">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg mx-2 transition-colors',
                isActive
                  ? 'bg-white/15 text-white'
                  : 'text-brand-200 hover:bg-white/10 hover:text-white',
              )}
            >
              <Icon size={18} />
              <span>{label}</span>
              <ChevronRight size={14} className="ml-auto opacity-40" />
            </NavLink>
          ))}
        </nav>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-3 text-sm text-brand-300 hover:text-white hover:bg-white/10 border-t border-brand-600 transition-colors"
        >
          <LogOut size={18} />
          Déconnexion
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
