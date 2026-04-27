import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

const PAGE_TITLES: Record<string, string> = {
  '/dashboard':    'Tableau de bord',
  '/agents':       'Yukpo Agents',
  '/validations':  'Validations humaines',
  '/chat':         'Yukpo Copilote',
  '/sinistres':    'Sinistres',
  '/souscription': 'Polices & Souscription',
  '/comptabilite': 'Comptabilité PCSA',
  '/reassurance':  'Réassurance',
  '/cima':         'Conformité CIMA',
  '/parametres':   'Paramètres',
}

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || 'YukpoAssurance'

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#f0f4f8' }}>
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header onMenuClick={() => setSidebarOpen(true)} title={title} />

        {/* Bande décorative Yukpo sous le header */}
        <div
          className="h-0.5 flex-shrink-0"
          style={{ background: 'linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)' }}
        />

        <main
          className="flex-1 overflow-auto"
          style={{ background: 'linear-gradient(160deg, #f0f4f8 0%, #e8eef5 100%)' }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
