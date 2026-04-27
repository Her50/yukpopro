import { NavLink, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import {
  LayoutDashboard, MessageSquare, LogOut, ChevronLeft, ChevronRight,
  ShieldCheck, CreditCard, Users, FileText, FolderOpen,
  Car, Scale, BarChart3, RefreshCw, CheckSquare, Settings,
} from "lucide-react";
import { cn, AssuranceLogo, Badge } from "@/components/ui";
import { useAuthStore, useUIStore } from "@/store";

const NAV_ITEMS = [
  // ── Primaire
  { path: "/chat",        icon: MessageSquare, label: "YukpoPro",       badge: "",  section: "primary", adminOnly: false },
  { path: "/validations", icon: CheckSquare,   label: "Validations",    badge: null,  section: "primary", adminOnly: false },
  // ── Modules métier
  { path: "/sinistres",   icon: ShieldCheck,   label: "Sinistres",      badge: null,  section: "modules", adminOnly: false },
  { path: "/souscription",icon: FileText,      label: "Souscription",   badge: null,  section: "modules", adminOnly: false },
  { path: "/comptabilite",icon: BarChart3,     label: "Comptabilité",   badge: null,  section: "modules", adminOnly: false },
  { path: "/cima",        icon: Scale,         label: "CIMA / Ratios",  badge: null,  section: "modules", adminOnly: false },
  { path: "/reassurance", icon: RefreshCw,     label: "Réassurance",    badge: null,  section: "modules", adminOnly: false },
  { path: "/documents",   icon: FolderOpen,    label: "Documents",      badge: null,  section: "modules", adminOnly: false },
  // ── Analytics
  { path: "/dashboard",   icon: LayoutDashboard, label: "Tableau de bord", badge: null, section: "analytics", adminOnly: false },
  // ── Compte
  { path: "/profil",      icon: Users,         label: "Mon Profil",     badge: null,  section: "compte",  adminOnly: false },
  { path: "/abonnement",  icon: CreditCard,    label: "Abonnement",     badge: null,  section: "compte",  adminOnly: false },
  // ── Admin
  { path: "/admin",       icon: Settings,      label: "Administration", badge: "ADM", section: "admin",   adminOnly: true  },
];

const SECTION_LABELS: Record<string, string> = {
  primary:   "Actions IA",
  modules:   "Modules",
  analytics: "Analyse",
  compte:    "Compte",
  admin:     "Admin",
};

export function Sidebar() {
  const collapsed           = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar       = useUIStore((s) => s.toggleSidebar);
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed);
  const { logout, user }    = useAuthStore();
  const navigate            = useNavigate();
  const isAdmin = ["admin", "super_admin"].includes(user?.role || "");

  useEffect(() => {
    const check = () => { if (window.innerWidth < 768) setSidebarCollapsed(true); };
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, [setSidebarCollapsed]);

  const handleLogout = () => { logout(); navigate("/login"); };

  const visibleItems = NAV_ITEMS.filter((i) => !i.adminOnly || isAdmin);

  // Group by section while preserving order
  const sections = Array.from(new Set(visibleItems.map((i) => i.section)));

  return (
    <aside
      className={cn(
        "flex flex-col h-screen transition-all duration-300 ease-in-out border-r border-white/[0.06]",
        collapsed ? "w-16" : "w-64"
      )}
      style={{ background: "#0D1117" }}
    >
      {/* Bande CIMA */}
      <div className="h-0.5 w-full" style={{ background: "linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)" }} />

      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-white/[0.06]">
        {collapsed ? (
          <div style={{
            width: 36, height: 36,
            background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)",
            borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 0 8px rgba(0,84,166,0.3)",
            margin: "0 auto",
          }}>
            <Car className="w-4 h-4 text-white" />
          </div>
        ) : (
          <AssuranceLogo size={26} />
        )}
      </div>

      {/* Profil synthétique */}
      {!collapsed && (
        <div className="mx-3 my-2 p-3 rounded-xl border border-white/[0.06]" style={{ background: "rgba(255,255,255,0.04)" }}>
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm flex-shrink-0 text-white",
              isAdmin ? "bg-red-500/20 border border-red-500/30" : "bg-assurance-500/20 border border-assurance-500/30"
            )}>
              {isAdmin ? <Settings className="w-4 h-4 text-red-400" /> : (user?.nom?.charAt(0).toUpperCase() || "G")}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white truncate">
                {isAdmin ? "Administrateur" : (user?.nom || "Gestionnaire")}
              </p>
              <p className="text-xs text-ciel-400 mt-0.5 truncate">
                {user?.compagnie_nom || "YukpoAssurance"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {sections.map((section) => {
          const items = visibleItems.filter((i) => i.section === section);
          return (
            <div key={section} className="mb-2">
              {!collapsed && (
                <p className="px-5 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-600">
                  {SECTION_LABELS[section]}
                </p>
              )}
              <ul className="space-y-0.5 px-2">
                {items.map(({ path, icon: Icon, label, badge }) => (
                  <li key={path}>
                    <NavLink
                      to={path}
                      className={({ isActive }) => cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 group relative border",
                        isActive
                          ? "text-ciel-300 border-assurance-500/20 bg-assurance-500/10"
                          : "text-gray-400 hover:text-gray-100 border-transparent hover:bg-white/[0.05] hover:border-white/[0.06]"
                      )}
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-ciel-400" />
                          )}
                          <Icon className={cn(
                            "w-5 h-5 flex-shrink-0",
                            isActive ? "text-ciel-400" : "text-gray-500 group-hover:text-gray-300"
                          )} />
                          {!collapsed && (
                            <>
                              <span className="flex-1">{label}</span>
                              {badge && <Badge variant="blue" size="xs">{badge}</Badge>}
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
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-white/[0.06] space-y-0.5">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-500 hover:text-gray-200 hover:bg-white/[0.05] transition-all border border-transparent"
        >
          {collapsed
            ? <ChevronRight className="w-5 h-5 mx-auto" />
            : <><ChevronLeft className="w-5 h-5" /><span>Réduire</span></>}
        </button>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-500 hover:text-red-400 hover:bg-red-500/[0.08] transition-all border border-transparent hover:border-red-500/20"
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Déconnexion</span>}
        </button>
      </div>
    </aside>
  );
}
