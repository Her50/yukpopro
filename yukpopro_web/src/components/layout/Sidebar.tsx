import { NavLink, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import {
  LayoutDashboard, MessageSquare, User, LogOut,
  ChevronLeft, ChevronRight, Sparkles, Shield, CreditCard,
  Users, Languages, FileText, FolderOpen, Briefcase, Gavel, ClipboardList,
} from "lucide-react";
import { cn, YukpoLogo, Badge } from "@/components/ui";
import { useAuthStore, useProfilStore, useUIStore } from "@/store";

const NAV_ITEMS = [
  { path: "/chat",          icon: MessageSquare,   label: "Yukpo Pro",       badge: "PRO", adminOnly: false },
  { path: "/traduction",    icon: Languages,       label: "Traduction",       badge: null,  adminOnly: false },
  { path: "/generateurs",   icon: FileText,        label: "Yukpo Studio",     badge: null,  adminOnly: false },
  { path: "/mes-documents", icon: FolderOpen,      label: "Mes Documents",    badge: null,  adminOnly: false },
  { path: "/reunions",      icon: Users,           label: "Réunions",         badge: null,  adminOnly: false },
  { path: "/emploi",        icon: Briefcase,       label: "Offres d'emploi",  badge: null,  adminOnly: false },
  { path: "/marches",       icon: Gavel,           label: "Appels d'offres",  badge: null,  adminOnly: false },
  { path: "/enquetes",      icon: ClipboardList,   label: "Enquêtes",         badge: null,  adminOnly: false },
  { path: "/dashboard",     icon: LayoutDashboard, label: "Tableau de bord",  badge: null,  adminOnly: false },
  { path: "/profil",        icon: User,            label: "Mon Profil",       badge: null,  adminOnly: false },
  { path: "/abonnement",    icon: CreditCard,      label: "Abonnement",       badge: null,  adminOnly: false },
  { path: "/admin",         icon: Shield,          label: "Administration",   badge: "ADM", adminOnly: true  },
];

export const Sidebar = () => {
  const collapsed          = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar      = useUIStore((s) => s.toggleSidebar);
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed);
  const { logout, user }   = useAuthStore();
  const { profil }         = useProfilStore();
  const navigate           = useNavigate();
  const isAdmin = ["admin", "super_admin", "yukpo_owner"].includes(user?.role || "");

  useEffect(() => {
    const check = () => { if (window.innerWidth < 768) setSidebarCollapsed(true); };
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <aside
      className={cn(
        "flex flex-col h-screen transition-all duration-300 ease-in-out border-r border-white/[0.06]",
        collapsed ? "w-16" : "w-64"
      )}
      style={{ background: "#0D1117" }}
    >
      {/* Barre de marque */}
      <div className="h-0.5 w-full" style={{ background: "linear-gradient(90deg, #7B3FE4, #06B6D4)" }} />

      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-white/[0.06]">
        {collapsed ? (
          <div className="mx-auto" style={{
            width: 36, height: 36, background: "white", borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 4,
            boxShadow: "0 0 0 1px rgba(123,63,228,0.3)",
          }}>
            <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
        ) : (
          <YukpoLogo size={28} />
        )}
      </div>

      {/* Profil */}
      {!collapsed && (
        <div className="mx-3 my-2 p-3 rounded-xl border border-white/[0.06]" style={{ background: "rgba(255,255,255,0.04)" }}>
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm flex-shrink-0 text-white",
              isAdmin ? "bg-red-500/20 border border-red-500/30" : "bg-yukpo-500/20 border border-yukpo-500/30"
            )}>
              {isAdmin ? <Shield className="w-4 h-4 text-red-400" /> : (profil?.metier?.charAt(0).toUpperCase() || "P")}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white truncate">
                {isAdmin ? "Administrateur" : (profil?.metier?.replace(/_/g, " ") || "Professionnel")}
              </p>
              <div className="flex items-center gap-1.5 mt-0.5">
                {isAdmin
                  ? <><Shield className="w-3 h-3 text-red-400" /><span className="text-xs text-red-400 font-medium">Accès total</span></>
                  : <><Sparkles className="w-3 h-3 text-gold-400" /><span className="text-xs text-gold-400 font-medium">{profil?.niveau_pro || "Starter"}</span></>
                }
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 py-2 overflow-y-auto">
        <ul className="space-y-0.5 px-2">
          {NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin).map(({ path, icon: Icon, label, badge }) => (
            <li key={path}>
              <NavLink
                to={path}
                className={({ isActive }) => cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 group relative border",
                  isActive
                    ? "text-yukpo-200 border-yukpo-500/20 bg-yukpo-500/10"
                    : "text-gray-400 hover:text-gray-100 border-transparent hover:bg-white/[0.05] hover:border-white/[0.06]"
                )}
              >
                {({ isActive }) => (
                  <>
                    {isActive && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-yukpo-400" />}
                    <Icon className={cn("w-5 h-5 flex-shrink-0", isActive ? "text-yukpo-400" : "text-gray-500 group-hover:text-gray-300")} />
                    {!collapsed && (
                      <>
                        <span className="flex-1">{label}</span>
                        {badge && <Badge variant="purple" size="sm">{badge}</Badge>}
                      </>
                    )}
                    {collapsed && (
                      <div className="absolute left-full ml-2 px-2.5 py-1.5 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 whitespace-nowrap z-50 pointer-events-none transition-opacity"
                        style={{ background: "#1F2937", border: "1px solid rgba(255,255,255,0.08)", boxShadow: "0 4px 12px rgba(0,0,0,0.4)" }}>
                        {label}
                      </div>
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-white/[0.06] space-y-0.5">
        <button onClick={toggleSidebar}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-500 hover:text-gray-200 hover:bg-white/[0.05] transition-all border border-transparent">
          {collapsed ? <ChevronRight className="w-5 h-5 mx-auto" /> : <><ChevronLeft className="w-5 h-5" /><span>Réduire</span></>}
        </button>
        <button onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-500 hover:text-red-400 hover:bg-red-500/[0.08] transition-all border border-transparent hover:border-red-500/20">
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Déconnexion</span>}
        </button>
      </div>
    </aside>
  );
};
