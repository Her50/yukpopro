import { Navigate, RouteObject } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Layout } from '../components/Layout'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { LoginPage } from '../pages/LoginPage'
import { DashboardPage } from '../pages/DashboardPage'
import { ChatPage } from '../pages/ChatPage'
import { DocumentsPage } from '../pages/DocumentsPage'
import AgentPage from '../pages/AgentPage'
import ValidationQueuePage from '../pages/ValidationQueuePage'
import SinistresPage from '../pages/SinistresPage'
import { CIMAPage } from '../pages/CIMAPage'
import { CourtiersPage } from '../pages/CourtiersPage'
import { RHPage } from '../pages/RHPage'
import { CommercialPage } from '../pages/CommercialPage'
import { SouscriptionPage } from '../pages/SouscriptionPage'
import TarificationPage from '../pages/TarificationPage'
import ComptabilitePage from '../pages/ComptabilitePage'
import ReassurancePage from '../pages/ReassurancePage'
import ParametresPage from '../pages/ParametresPage'
import FournisseurPage from '../pages/FournisseurPage'
import ReunionPage from '../pages/ReunionPage'
import { CommissionsPage } from '../pages/CommissionsPage'
import ServiceJuridiquePage from '../pages/ServiceJuridiquePage'
import { useAuthStore } from '../store/authStore'
import { ReactNode } from 'react'

// Lazy loading pour les pages secondaires (code splitting)
const TrendsPage = lazy(() => import('../pages/TrendsPage'))
const AgendaPage = lazy(() => import('../pages/AgendaPage'))
const CommunityManagerPage = lazy(() => import('../pages/CommunityManagerPage'))

const PageFallback = () => (
  <div className="flex items-center justify-center h-48">
    <LoadingSpinner />
  </div>
)

function ProtectedRoute({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Enveloppe une page avec ErrorBoundary + Suspense */
function Page({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageFallback />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  )
}

export const routes: RouteObject[] = [
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <Page><DashboardPage /></Page> },
      { path: 'agents', element: <Page><AgentPage /></Page> },
      { path: 'validations', element: <Page><ValidationQueuePage /></Page> },
      { path: 'chat', element: <Page><ChatPage /></Page> },
      { path: 'sinistres', element: <Page><SinistresPage /></Page> },
      { path: 'souscription', element: <Page><SouscriptionPage /></Page> },
      { path: 'documents', element: <Page><DocumentsPage /></Page> },
      { path: 'cima', element: <Page><CIMAPage /></Page> },
      { path: 'courtiers', element: <Page><CourtiersPage /></Page> },
      { path: 'commercial', element: <Page><CommercialPage /></Page> },
      { path: 'rh', element: <Page><RHPage /></Page> },
      { path: 'tarification', element: <Navigate to="/souscription" replace /> },
      { path: 'comptabilite', element: <Page><ComptabilitePage /></Page> },
      { path: 'reassurance', element: <Page><ReassurancePage /></Page> },
      { path: 'parametres', element: <Page><ParametresPage /></Page> },
      { path: 'trends', element: <Page><TrendsPage /></Page> },
      { path: 'agenda', element: <Navigate to="/reunions" replace /> },
      { path: 'community-manager', element: <Page><CommunityManagerPage /></Page> },
      { path: 'fournisseurs', element: <Page><FournisseurPage /></Page> },
      { path: 'reunions', element: <Page><ReunionPage /></Page> },
      { path: 'commissions', element: <Page><CommissionsPage /></Page> },
      { path: 'juridique', element: <Page><ServiceJuridiquePage /></Page> },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]
