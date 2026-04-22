import { Outlet, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { Sidebar } from "./Sidebar";
import { useAuthStore } from "@/store";

export const AppLayout = () => {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-[100dvh] overflow-hidden" style={{ background: "#111827" }}>
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-y-auto min-w-0" style={{ background: "#111827" }}>
        <Outlet />
      </main>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "#1F2937",
            color: "#F9FAFB",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "12px",
            fontSize: "14px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
          },
          success: { iconTheme: { primary: "#7B3FE4", secondary: "#fff" } },
          error:   { iconTheme: { primary: "#EF4444", secondary: "#fff" } },
        }}
      />
    </div>
  );
};
