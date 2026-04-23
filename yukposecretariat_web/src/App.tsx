import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import RedactionPage from './pages/RedactionPage'
import OcrPage from './pages/OcrPage'
import AudioPage from './pages/AudioPage'
import InfographiePage from './pages/InfographiePage'
import KanbanPage from './pages/KanbanPage'
import DevisPage from './pages/DevisPage'
import CaissePage from './pages/CaissePage'
import ClientsPage from './pages/ClientsPage'
import TraductionPage from './pages/TraductionPage'
import MesDocumentsPage from './pages/MesDocumentsPage'
import AbonnementPage from './pages/AbonnementPage'

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
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="redaction" element={<RedactionPage />} />
        <Route path="ocr" element={<OcrPage />} />
        <Route path="audio" element={<AudioPage />} />
        <Route path="infographie" element={<InfographiePage />} />
        <Route path="traduction" element={<TraductionPage />} />
        <Route path="documents" element={<MesDocumentsPage />} />
        <Route path="kanban" element={<KanbanPage />} />
        <Route path="devis" element={<DevisPage />} />
        <Route path="caisse" element={<CaissePage />} />
        <Route path="clients" element={<ClientsPage />} />
        <Route path="abonnement" element={<AbonnementPage />} />
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
