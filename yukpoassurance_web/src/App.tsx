import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoginPage }       from "@/pages/LoginPage";
import { ChatPage }        from "@/pages/ChatPage";
import { DashboardPage }   from "@/pages/DashboardPage";
import { ValidationPage }  from "@/pages/ValidationPage";
import { SinistresPage }   from "@/pages/SinistresPage";
import { SouscriptionPage} from "@/pages/SouscriptionPage";
import { ComptabilitePage} from "@/pages/ComptabilitePage";
import { CIMAPage }        from "@/pages/CIMAPage";
import { ReassurancePage } from "@/pages/ReassurancePage";
import { DocumentsPage }   from "@/pages/DocumentsPage";
import { ProfilPage }      from "@/pages/ProfilPage";
import { AbonnementPage }  from "@/pages/AbonnementPage";
import { AdminPage }       from "@/pages/AdminPage";

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
            <Route path="/"             element={<Navigate to="/chat" replace />} />
            <Route path="/chat"         element={<ChatPage />} />
            <Route path="/validations"  element={<ValidationPage />} />
            <Route path="/dashboard"    element={<DashboardPage />} />
            <Route path="/sinistres"    element={<SinistresPage />} />
            <Route path="/souscription" element={<SouscriptionPage />} />
            <Route path="/comptabilite" element={<ComptabilitePage />} />
            <Route path="/cima"         element={<CIMAPage />} />
            <Route path="/reassurance"  element={<ReassurancePage />} />
            <Route path="/documents"    element={<DocumentsPage />} />
            <Route path="/profil"       element={<ProfilPage />} />
            <Route path="/abonnement"   element={<AbonnementPage />} />
            <Route path="/admin"        element={<AdminPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
