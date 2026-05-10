import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ChatPage from './pages/ChatPage'
import AnalyticsPage from './pages/AnalyticsPage'
import AdminPage from './pages/AdminPage'
import KanbanPage from './pages/KanbanPage'
import DevisPage from './pages/DevisPage'
import CaissePage from './pages/CaissePage'
import ClientsPage from './pages/ClientsPage'
import MesDocumentsPage from './pages/MesDocumentsPage'
import AbonnementPage from './pages/AbonnementPage'
import OrganisationPage from './pages/OrganisationPage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex h-screen items-center justify-center text-brand-600 text-lg">Chargement…</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
        {/* Sprint S1 — Chat Unifié = page d'entrée par défaut (zero-config) */}
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        {/* Sprint chat-only — toutes les capacités de génération sont dans /chat.
            Routes legacy conservées en redirect pour bookmarks/e-mails/documents.
            i18n keys nav.redaction/nav.infographie/nav.traduction restent dispos
            pour la doc/FAQ/onboarding mais ne sont plus lues par le menu. */}
        <Route path="redaction"     element={<Navigate to="/chat" replace />} />
        <Route path="ocr"           element={<Navigate to="/chat" replace />} />
        <Route path="audio"         element={<Navigate to="/chat" replace />} />
        <Route path="scanner"       element={<Navigate to="/chat" replace />} />
        <Route path="infographie"   element={<Navigate to="/chat" replace />} />
        <Route path="designer"      element={<Navigate to="/chat" replace />} />
        <Route path="designer-pro"  element={<Navigate to="/chat" replace />} />
        <Route path="visuels"       element={<Navigate to="/chat" replace />} />
        <Route path="flyer"         element={<Navigate to="/chat" replace />} />
        <Route path="traduction"    element={<Navigate to="/chat" replace />} />
        <Route path="traduire"      element={<Navigate to="/chat" replace />} />
        <Route path="translate"     element={<Navigate to="/chat" replace />} />
        <Route path="conversion"    element={<Navigate to="/chat" replace />} />
        <Route path="convertir"     element={<Navigate to="/chat" replace />} />
        <Route path="rapports"      element={<Navigate to="/chat" replace />} />
        <Route path="slides"        element={<Navigate to="/chat" replace />} />
        <Route path="documents-ia"  element={<Navigate to="/chat" replace />} />
        <Route path="documents" element={<MesDocumentsPage />} />
        <Route path="kanban" element={<KanbanPage />} />
        <Route path="devis" element={<DevisPage />} />
        <Route path="caisse" element={<CaissePage />} />
        <Route path="clients" element={<ClientsPage />} />
        <Route path="abonnement" element={<AbonnementPage />} />
        <Route path="organisation" element={<OrganisationPage />} />
        <Route path="admin" element={<AdminPage />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
