import { Outlet, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { Sidebar } from "./Sidebar";
import { useAuthStore } from "@/store";

export const AppLayout = () => {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-[100dvh] overflow-hidden" style={{ background: "#162033" }}>
      <Sidebar />

      {/* Zone contenu principale */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* Barre supérieure — gradient corporate DS */}
        <header
          className="h-1.5 w-full flex-shrink-0"
          style={{ background: "linear-gradient(90deg, #0054A6 0%, #00B0F0 50%, #0054A6 100%)" }}
          aria-hidden="true"
        />

        <main
          className="flex-1 overflow-y-auto min-w-0"
          style={{ background: "linear-gradient(160deg, #1e2640 0%, #162033 100%)" }}
        >
          <Outlet />
        </main>
      </div>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "#243050",
            color: "#E2E8F0",
            border: "1px solid rgba(99,102,241,0.2)",
            borderRadius: "10px",
            fontSize: "14px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)",
          },
          success: { iconTheme: { primary: "#10b981", secondary: "#fff" } },
          error:   { iconTheme: { primary: "#ef4444", secondary: "#fff" } },
        }}
      />
    </div>
  );
};
