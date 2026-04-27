import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "@/components/layout/AppLayout";
import { PWAInstallBanner } from "@/components/PWAInstallBanner";

const LoginPage = lazy(() => import("@/pages/LoginPage").then(m => ({ default: m.LoginPage })));
const ChatPage = lazy(() => import("@/pages/ChatPage").then(m => ({ default: m.ChatPage })));
const DashboardPage = lazy(() => import("@/pages/DashboardPage").then(m => ({ default: m.DashboardPage })));
const ProfilPage = lazy(() => import("@/pages/ProfilPage").then(m => ({ default: m.ProfilPage })));
const AdminPage = lazy(() => import("@/pages/AdminPage").then(m => ({ default: m.AdminPage })));
const AdminPaiementsPage = lazy(() => import("@/pages/AdminPaiementsPage").then(m => ({ default: m.AdminPaiementsPage })));
const AbonnementPage = lazy(() => import("@/pages/AbonnementPage").then(m => ({ default: m.AbonnementPage })));
const WalletPage = lazy(() => import("@/pages/WalletPage").then(m => ({ default: m.WalletPage })));
const ReunionsPage = lazy(() => import("@/pages/ReunionsPage").then(m => ({ default: m.ReunionsPage })));
const TraductionPage = lazy(() => import("@/pages/TraductionPage").then(m => ({ default: m.TraductionPage })));
const TranslateLivePage = lazy(() => import("@/pages/TranslateLivePage").then(m => ({ default: m.TranslateLivePage })));
const GenerateursPage = lazy(() => import("@/pages/GenerateursPage").then(m => ({ default: m.GenerateursPage })));
const HistoriqueDocumentsPage = lazy(() => import("@/pages/HistoriqueDocumentsPage").then(m => ({ default: m.HistoriqueDocumentsPage })));
const EmploiPage = lazy(() => import("@/pages/EmploiPage").then(m => ({ default: m.EmploiPage })));
const MarchesPage = lazy(() => import("@/pages/MarchesPage").then(m => ({ default: m.MarchesPage })));
const EnquetesPage = lazy(() => import("@/pages/EnquetesPage").then(m => ({ default: m.EnquetesPage })));
const PublicFormPage = lazy(() => import("@/pages/PublicFormPage").then(m => ({ default: m.PublicFormPage })));
const ParametresPage = lazy(() => import("@/pages/ParametresPage").then(m => ({ default: m.ParametresPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5 * 60 * 1000 },
  },
});

const PageFallback = () => (
  <div className="flex items-center justify-center min-h-screen bg-slate-950">
    <div className="h-8 w-8 rounded-full border-2 border-violet-500 border-t-transparent animate-spin" />
  </div>
);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PWAInstallBanner />
      <BrowserRouter>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/formulaire/:formulaireId" element={<PublicFormPage />} />

            {/* Protected */}
            <Route element={<AppLayout />}>
              {/* YukpoPro est la page principale */}
              <Route path="/"            element={<Navigate to="/chat" replace />} />
              <Route path="/chat"        element={<ChatPage />} />
              <Route path="/reunions"    element={<ReunionsPage />} />
              <Route path="/dashboard"   element={<DashboardPage />} />
              <Route path="/profil"      element={<ProfilPage />} />
              <Route path="/wallet"      element={<WalletPage />} />
              <Route path="/abonnement"  element={<AbonnementPage />} />
              <Route path="/admin"       element={<AdminPage />} />
              <Route path="/admin/paiements" element={<AdminPaiementsPage />} />
              {/* Pages actives */}
              <Route path="/traduction"     element={<TraductionPage />} />
              <Route path="/translate-live" element={<TranslateLivePage />} />
              <Route path="/generateurs"    element={<GenerateursPage />} />
              <Route path="/mes-documents"  element={<HistoriqueDocumentsPage />} />
              <Route path="/emploi"         element={<EmploiPage />} />
              <Route path="/marches"        element={<MarchesPage />} />
              <Route path="/enquetes"       element={<EnquetesPage />} />
              <Route path="/parametres"     element={<ParametresPage />} />
              {/* Redirections legacy */}
              <Route path="/copilote"    element={<Navigate to="/chat" replace />} />
              <Route path="/agents"      element={<Navigate to="/chat" replace />} />
              <Route path="/analyse"     element={<Navigate to="/chat" replace />} />
            </Route>

            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
