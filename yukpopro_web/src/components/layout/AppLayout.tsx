import { Outlet, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { Sidebar } from "./Sidebar";
import { useAuthStore } from "@/store";

export const AppLayout = () => {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <div
      className="flex h-[100dvh] overflow-hidden"
      style={{ background: "var(--ykp-canvas)" }}
    >
      <Sidebar />

      {/* Zone contenu principale */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* Barre supérieure — gradient corporate DS (inchangé : identité de marque) */}
        <header
          className="h-1.5 w-full flex-shrink-0"
          style={{ background: "linear-gradient(90deg, #0054A6 0%, #00B0F0 50%, #0054A6 100%)" }}
          aria-hidden="true"
        />

        <main
          className="ykp-page flex-1 overflow-y-auto min-w-0"
          style={{ background: "var(--ykp-canvas-gradient)" }}
        >
          <Outlet />
        </main>
      </div>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "var(--ykp-toast-bg)",
            color: "var(--ykp-toast-text)",
            border: "1px solid var(--ykp-toast-border)",
            borderRadius: "10px",
            fontSize: "14px",
            boxShadow: "var(--ykp-shadow-elevated)",
          },
          success: { iconTheme: { primary: "#10b981", secondary: "#fff" } },
          error:   { iconTheme: { primary: "#ef4444", secondary: "#fff" } },
        }}
      />
    </div>
  );
};
