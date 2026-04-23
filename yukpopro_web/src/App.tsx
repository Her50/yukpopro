import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoginPage } from "@/pages/LoginPage";
import { ChatPage } from "@/pages/ChatPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ProfilPage } from "@/pages/ProfilPage";
import { AdminPage } from "@/pages/AdminPage";
import { AbonnementPage } from "@/pages/AbonnementPage";
import { ReunionsPage } from "@/pages/ReunionsPage";
import { TraductionPage } from "@/pages/TraductionPage";
import { TranslateLivePage } from "@/pages/TranslateLivePage";
import { GenerateursPage } from "@/pages/GenerateursPage";
import { HistoriqueDocumentsPage } from "@/pages/HistoriqueDocumentsPage";
import { EmploiPage } from "@/pages/EmploiPage";
import { MarchesPage } from "@/pages/MarchesPage";
import { EnquetesPage } from "@/pages/EnquetesPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5 * 60 * 1000 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected */}
          <Route element={<AppLayout />}>
            {/* YukpoPro est la page principale */}
            <Route path="/"            element={<Navigate to="/chat" replace />} />
            <Route path="/chat"        element={<ChatPage />} />
            <Route path="/reunions"    element={<ReunionsPage />} />
            <Route path="/dashboard"   element={<DashboardPage />} />
            <Route path="/profil"      element={<ProfilPage />} />
            <Route path="/abonnement"  element={<AbonnementPage />} />
            <Route path="/admin"       element={<AdminPage />} />
            {/* Pages actives */}
            <Route path="/traduction"     element={<TraductionPage />} />
            <Route path="/translate-live" element={<TranslateLivePage />} />
            <Route path="/generateurs"    element={<GenerateursPage />} />
            <Route path="/mes-documents"  element={<HistoriqueDocumentsPage />} />
            <Route path="/emploi"         element={<EmploiPage />} />
            <Route path="/marches"        element={<MarchesPage />} />
            <Route path="/enquetes"       element={<EnquetesPage />} />
            {/* Redirections legacy */}
            <Route path="/copilote"    element={<Navigate to="/chat" replace />} />
            <Route path="/agents"      element={<Navigate to="/chat" replace />} />
            <Route path="/analyse"     element={<Navigate to="/chat" replace />} />
          </Route>

          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
