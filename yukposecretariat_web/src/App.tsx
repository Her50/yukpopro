import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ChatPage from './pages/ChatPage'
import AnalyticsPage from './pages/AnalyticsPage'
import RedactionPage from './pages/RedactionPage'
import InfographiePage from './pages/InfographiePage'
import AdminPage from './pages/AdminPage'
import KanbanPage from './pages/KanbanPage'
import DevisPage from './pages/DevisPage'
import CaissePage from './pages/CaissePage'
import ClientsPage from './pages/ClientsPage'
import TraductionPage from './pages/TraductionPage'
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
        <Route path="redaction" element={<RedactionPage />} />
        {/* Anciennes routes redirigées vers le hub Rédaction IA (avec onglet pré-sélectionné) */}
        <Route path="ocr"   element={<Navigate to="/redaction?tab=scan"  replace />} />
        <Route path="audio" element={<Navigate to="/redaction?tab=audio" replace />} />
        <Route path="infographie" element={<InfographiePage />} />
        <Route path="traduction" element={<TraductionPage />} />
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
