/**
 * AdminPage — YukpoPro
 *
 * Wrapper qui monte le composant partagé <AdminDashboard> de
 * @yukpo/admin-dashboard (sources dans packages/admin-dashboard/src/).
 * La même page existe dans yukposecretariat_web — toutes deux affichent
 * le même dashboard cross-app avec un sélecteur de scope (Pro / Sec /
 * Both) persisté en localStorage.
 *
 * Endpoints consommés (via http injecté) : /api/v1/admin-cross/*
 *
 * Les routes admin spécifiques YukpoPro (/api/v1/pro/admin/*) — gestion
 * utilisateurs, bonus crédits, blocage, promotions — restent live côté
 * backend et seront ré-exposées ultérieurement comme sous-onglets du
 * dashboard partagé. La version pré-refonte est conservée dans git
 * (commit antérieur à la fusion admin-cross).
 */
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { AdminDashboard } from "@yukpo/admin-dashboard";
import { http } from "@/api/client";
import { useAuthStore } from "@/store";

export const AdminPage = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();

  // Garde-fou client (le backend refuse aussi via _require_admin)
  useEffect(() => {
    if (!user) return;
    const isAdmin = ["admin", "super_admin", "yukpo_owner"].includes(user.role);
    if (!isAdmin) navigate("/chat", { replace: true });
  }, [user, navigate]);

  return (
    <div className="px-4 sm:px-6 py-6 max-w-7xl mx-auto">
      <AdminDashboard
        http={http}
        appLabel="YukpoPro"
        defaultScope="both"
        storageKey="yukpo_admin_cross_scope"
      />
    </div>
  );
};
