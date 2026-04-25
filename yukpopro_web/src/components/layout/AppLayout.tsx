import { Outlet, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { useAuthStore, useUIStore } from "@/store";

export const AppLayout = () => {
  const { isAuthenticated } = useAuthStore();
  const setMobileSidebarOpen = useUIStore((s) => s.setMobileSidebarOpen);

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <div
      className="flex h-[100dvh] overflow-hidden"
      style={{ background: "var(--ykp-canvas)" }}
    >
      <Sidebar />

      {/* Zone contenu principale */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* Header mobile — visible uniquement sur < 640px */}
        <div
          className="sm:hidden flex items-center gap-3 px-4 h-14 flex-shrink-0 border-b"
          style={{
            background: "var(--ykp-sidebar-start)",
            borderColor: "var(--ykp-sidebar-border)",
          }}
        >
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="p-2 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Ouvrir le menu"
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div style={{
              width: 44, height: 44, background: "white", borderRadius: 11,
              display: "flex", alignItems: "center", justifyContent: "center", padding: 4,
              boxShadow: "0 0 0 1px rgba(255,255,255,0.18), 0 4px 10px rgba(0,0,0,0.3)",
            }}>
              <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            </div>
            <span className="text-white font-bold text-base">Yukpo<span style={{ color: "#00B0F0" }}>Pro</span></span>
          </div>
        </div>

        {/* Barre supérieure — gradient corporate DS */}
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
