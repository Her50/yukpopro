import { NavLink, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import {
  LayoutDashboard, MessageSquare, User, LogOut,
  ChevronLeft, ChevronRight, Sparkles, Shield, CreditCard,
  Users, Languages, FileText, FolderOpen, Briefcase, Gavel, ClipboardList, Radio,
} from "lucide-react";
import { cn, YukpoLogo, Badge } from "@/components/ui";
import { useAuthStore, useProfilStore, useUIStore } from "@/store";

const NAV_ITEMS = [
  { path: "/chat",           icon: MessageSquare,   label: "Yukpo Pro",       badge: "PRO", adminOnly: false },
  { path: "/traduction",     icon: Languages,       label: "Traduction",       badge: null,  adminOnly: false },
  { path: "/translate-live", icon: Radio,           label: "Traduction Live",  badge: "NEW", adminOnly: false },
  { path: "/generateurs",    icon: FileText,        label: "Yukpo Studio",     badge: null,  adminOnly: false },
  { path: "/mes-documents",  icon: FolderOpen,      label: "Mes Documents",    badge: null,  adminOnly: false },
  { path: "/reunions",       icon: Users,           label: "Réunions",         badge: null,  adminOnly: false },
  { path: "/emploi",         icon: Briefcase,       label: "Offres d'emploi",  badge: null,  adminOnly: false },
  { path: "/marches",        icon: Gavel,           label: "Appels d'offres",  badge: null,  adminOnly: false },
  { path: "/enquetes",       icon: ClipboardList,   label: "Enquêtes",         badge: null,  adminOnly: false },
  { path: "/dashboard",      icon: LayoutDashboard, label: "Tableau de bord",  badge: null,  adminOnly: false },
  { path: "/profil",         icon: User,            label: "Mon Profil",       badge: null,  adminOnly: false },
  { path: "/abonnement",     icon: CreditCard,      label: "Abonnement",       badge: null,  adminOnly: false },
  { path: "/admin",          icon: Shield,          label: "Administration",   badge: "ADM", adminOnly: true  },
];

export const Sidebar = () => {
  const collapsed           = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar       = useUIStore((s) => s.toggleSidebar);
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed);
  const { logout, user }    = useAuthStore();
  const { profil }          = useProfilStore();
  const navigate            = useNavigate();
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
        "flex flex-col h-screen flex-shrink-0 transition-all duration-300 ease-in-out",
        "border-r border-white/[0.06]",
        collapsed ? "w-16" : "w-64"
      )}
      style={{ background: "linear-gradient(180deg, #1e2640 0%, #162033 100%)" }}
    >
      {/* Filet supérieur — gradient corporate */}
      <div
        className="h-0.5 w-full flex-shrink-0"
        style={{ background: "linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)" }}
        aria-hidden="true"
      />

      {/* Logo */}
      <div className={cn(
        "flex items-center h-14 border-b border-white/[0.06] flex-shrink-0",
        collapsed ? "justify-center px-2" : "px-4"
      )}>
        {collapsed ? (
          <div style={{
            width: 34, height: 34, background: "white", borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 3,
            boxShadow: "0 0 0 1px rgba(0,84,166,0.4), 0 4px 12px rgba(0,84,166,0.2)",
          }}>
            <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
        ) : (
          <YukpoLogo size={26} />
        )}
      </div>

      {/* Profil utilisateur */}
      {!collapsed && (
        <div className="mx-3 my-2.5 p-3 rounded-xl" style={{
          background: "rgba(255,255,255,0.05)",
          border: "1px solid rgba(255,255,255,0.07)",
        }}>
          <div className="flex items-center gap-3">
            {/* Avatar */}
            <div className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs flex-shrink-0 text-white",
            )} style={{
              background: isAdmin
                ? "linear-gradient(135deg, #991b1b, #7f1d1d)"
                : "linear-gradient(135deg, #0054A6, #003476)",
              boxShadow: isAdmin
                ? "0 0 0 1px rgba(239,68,68,0.3)"
                : "0 0 0 1px rgba(0,84,166,0.4)",
            }}>
              {isAdmin ? <Shield className="w-4 h-4 text-red-300" /> : (
                <span className="text-white">{profil?.metier?.charAt(0).toUpperCase() || "P"}</span>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-100 truncate leading-tight">
                {isAdmin ? "Administrateur" : (profil?.metier?.replace(/_/g, " ") || "Professionnel")}
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                {isAdmin ? (
                  <><Shield className="w-3 h-3 text-red-400" /><span className="text-xs text-red-400 font-medium">Accès total</span></>
                ) : (
                  <><Sparkles className="w-3 h-3 text-gold-400" /><span className="text-xs text-gold-400 font-medium">{profil?.niveau_pro || "Starter"}</span></>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 py-2 overflow-y-auto" aria-label="Navigation principale">
        <ul className="space-y-0.5 px-2">
          {NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin).map(({ path, icon: Icon, label, badge }) => (
            <li key={path}>
              <NavLink
                to={path}
                className={({ isActive }) => cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium",
                  "transition-all duration-150 group relative",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-yukpo-400 focus-visible:ring-offset-1 focus-visible:ring-offset-navy-900",
                  isActive
                    ? "text-white"
                    : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.05]"
                )}
                style={({ isActive }) => isActive ? {
                  background: "linear-gradient(90deg, rgba(0,84,166,0.25) 0%, rgba(99,102,241,0.15) 100%)",
                  borderLeft: "2px solid #0054A6",
                  boxShadow: "inset 0 0 0 1px rgba(0,176,240,0.12)",
                } : undefined}
              >
                {({ isActive }) => (
                  <>
                    <Icon className={cn(
                      "w-4 h-4 flex-shrink-0 transition-colors",
                      isActive ? "text-bright-400" : "text-slate-500 group-hover:text-slate-300"
                    )} />
                    {!collapsed && (
                      <>
                        <span className="flex-1 truncate">{label}</span>
                        {badge && <Badge variant="corp" size="sm">{badge}</Badge>}
                      </>
                    )}
                    {/* Tooltip collapsed */}
                    {collapsed && (
                      <div
                        className="absolute left-full ml-3 px-3 py-1.5 text-slate-100 text-xs rounded-lg opacity-0 group-hover:opacity-100 whitespace-nowrap z-50 pointer-events-none transition-opacity duration-150"
                        style={{ background: "#1e2640", border: "1px solid rgba(0,84,166,0.3)", boxShadow: "0 4px 16px rgba(0,0,0,0.5)" }}
                      >
                        {label}
                        {badge && <span className="ml-2 text-bright-400 font-semibold">{badge}</span>}
                      </div>
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Diviseur graphique */}
      {!collapsed && (
        <div className="mx-4 my-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(0,84,166,0.4), transparent)" }} aria-hidden="true" />
      )}

      {/* Footer */}
      <div className="p-2 space-y-0.5 flex-shrink-0">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-slate-500 hover:text-slate-300 hover:bg-white/[0.04] transition-all"
          aria-label={collapsed ? "Développer la barre latérale" : "Réduire la barre latérale"}
        >
          {collapsed
            ? <ChevronRight className="w-4 h-4 mx-auto" />
            : <><ChevronLeft className="w-4 h-4" /><span>Réduire</span></>}
        </button>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-slate-500 hover:text-red-300 hover:bg-red-900/20 transition-all"
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Déconnexion</span>}
        </button>
      </div>
    </aside>
  );
};
