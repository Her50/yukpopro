import { Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "@/components/layout/AppLayout";
import { PWAInstallBanner } from "@/components/PWAInstallBanner";
import { lazyWithRetry, clearChunkReloadMarker } from "@/utils/lazyWithRetry";

// lazyWithRetry : si un chunk JS échoue à charger (cas typique après un
// déploiement où le SW PWA a précaché un index.html référençant des hash
// de chunks qui ont disparu du CDN), on force window.location.reload() pour
// récupérer le nouveau manifest. Évite le symptôme « page sombre au clic,
// résolu par F5 » (Suspense reste sur fallback bg-slate-950 sinon).
const LoginPage = lazyWithRetry(() => import("@/pages/LoginPage").then(m => ({ default: m.LoginPage })));
const ChatPage = lazyWithRetry(() => import("@/pages/ChatPage").then(m => ({ default: m.ChatPage })));
const DashboardPage = lazyWithRetry(() => import("@/pages/DashboardPage").then(m => ({ default: m.DashboardPage })));
const ProfilPage = lazyWithRetry(() => import("@/pages/ProfilPage").then(m => ({ default: m.ProfilPage })));
const AdminPage = lazyWithRetry(() => import("@/pages/AdminPage").then(m => ({ default: m.AdminPage })));
const AdminPaiementsPage = lazyWithRetry(() => import("@/pages/AdminPaiementsPage").then(m => ({ default: m.AdminPaiementsPage })));
const AbonnementPage = lazyWithRetry(() => import("@/pages/AbonnementPage").then(m => ({ default: m.AbonnementPage })));
const WalletPage = lazyWithRetry(() => import("@/pages/WalletPage").then(m => ({ default: m.WalletPage })));
const ReunionsPage = lazyWithRetry(() => import("@/pages/ReunionsPage").then(m => ({ default: m.ReunionsPage })));
const TranslateLivePage = lazyWithRetry(() => import("@/pages/TranslateLivePage").then(m => ({ default: m.TranslateLivePage })));
const HistoriqueDocumentsPage = lazyWithRetry(() => import("@/pages/HistoriqueDocumentsPage").then(m => ({ default: m.HistoriqueDocumentsPage })));
const EmploiPage = lazyWithRetry(() => import("@/pages/EmploiPage").then(m => ({ default: m.EmploiPage })));
const MarchesPage = lazyWithRetry(() => import("@/pages/MarchesPage").then(m => ({ default: m.MarchesPage })));
const EnquetesPage = lazyWithRetry(() => import("@/pages/EnquetesPage").then(m => ({ default: m.EnquetesPage })));
const PublicFormPage = lazyWithRetry(() => import("@/pages/PublicFormPage").then(m => ({ default: m.PublicFormPage })));
const ParametresPage = lazyWithRetry(() => import("@/pages/ParametresPage").then(m => ({ default: m.ParametresPage })));
const OrganisationPage = lazyWithRetry(() => import("@/pages/OrganisationPage").then(m => ({ default: m.OrganisationPage })));
const InviteAcceptPage = lazyWithRetry(() => import("@/pages/InviteAcceptPage").then(m => ({ default: m.InviteAcceptPage })));

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
  // Si on est arrivé ici, l'app a démarré correctement → clear le marker
  // anti-boucle de lazyWithRetry pour ne pas bloquer un futur retry légitime.
  useEffect(() => { clearChunkReloadMarker(); }, []);

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
              <Route path="/translate-live" element={<TranslateLivePage />} />
              <Route path="/mes-documents"  element={<HistoriqueDocumentsPage />} />
              <Route path="/emploi"         element={<EmploiPage />} />
              <Route path="/marches"        element={<MarchesPage />} />
              <Route path="/enquetes"       element={<EnquetesPage />} />
              <Route path="/parametres"     element={<ParametresPage />} />
              <Route path="/organisation"   element={<OrganisationPage />} />
              <Route path="/orgs/invites/:token" element={<InviteAcceptPage />} />
              {/* Redirections legacy — ces fonctions sont désormais dans le chat.
                  /translate-live est conservé séparément (live conversationnel). */}
              <Route path="/copilote"               element={<Navigate to="/chat" replace />} />
              <Route path="/agents"                 element={<Navigate to="/chat" replace />} />
              <Route path="/analyse"                element={<Navigate to="/chat" replace />} />
              <Route path="/traduction"             element={<Navigate to="/chat" replace />} />
              <Route path="/traduire"               element={<Navigate to="/chat" replace />} />
              <Route path="/translate"              element={<Navigate to="/chat" replace />} />
              <Route path="/generateurs"            element={<Navigate to="/chat" replace />} />
              <Route path="/generateurs/redaction"  element={<Navigate to="/chat" replace />} />
              <Route path="/redaction"              element={<Navigate to="/chat" replace />} />
              <Route path="/rapports"               element={<Navigate to="/chat" replace />} />
              <Route path="/slides"                 element={<Navigate to="/chat" replace />} />
              <Route path="/documents-ia"           element={<Navigate to="/chat" replace />} />
              <Route path="/studio"                 element={<Navigate to="/chat" replace />} />
              <Route path="/studio-pro"             element={<Navigate to="/chat" replace />} />
              <Route path="/designer"               element={<Navigate to="/chat" replace />} />
              <Route path="/designer-pro"           element={<Navigate to="/chat" replace />} />
              <Route path="/infographie"            element={<Navigate to="/chat" replace />} />
              <Route path="/infographie-pro"        element={<Navigate to="/chat" replace />} />
              <Route path="/visuels"                element={<Navigate to="/chat" replace />} />
              <Route path="/flyer"                  element={<Navigate to="/chat" replace />} />
              <Route path="/conversion"             element={<Navigate to="/chat" replace />} />
              <Route path="/convertir"              element={<Navigate to="/chat" replace />} />
              <Route path="/convert"                element={<Navigate to="/chat" replace />} />
              <Route path="/ocr"                    element={<Navigate to="/chat" replace />} />
              <Route path="/scanner"                element={<Navigate to="/chat" replace />} />
            </Route>

            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
