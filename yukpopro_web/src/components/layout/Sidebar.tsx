import { NavLink, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard, MessageSquare, User, LogOut,
  ChevronLeft, ChevronRight, Sparkles, Shield, CreditCard,
  Users, Languages, FileText, FolderOpen, Briefcase, Gavel, ClipboardList, Radio,
  Sun, Moon, Settings,
} from "lucide-react";
import { cn, YukpoLogo, Badge } from "@/components/ui";
import { useAuthStore, useProfilStore, useUIStore } from "@/store";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

const NAV_KEYS = [
  { path: "/chat",           icon: MessageSquare,   key: "chat",           badge: "PRO", adminOnly: false },
  { path: "/generateurs",    icon: FileText,        key: "generateurs",    badge: null,  adminOnly: false },
  { path: "/reunions",       icon: Users,           key: "reunions",       badge: null,  adminOnly: false },
  { path: "/mes-documents",  icon: FolderOpen,      key: "documents",      badge: null,  adminOnly: false },
  { path: "/traduction",     icon: Languages,       key: "traduction",     badge: null,  adminOnly: false },
  { path: "/translate-live", icon: Radio,           key: "translateLive",  badge: "NEW", adminOnly: false },
  { path: "/emploi",         icon: Briefcase,       key: "emploi",         badge: null,  adminOnly: false },
  { path: "/marches",        icon: Gavel,           key: "marches",        badge: null,  adminOnly: false },
  { path: "/enquetes",       icon: ClipboardList,   key: "enquetes",       badge: null,  adminOnly: false },
  { path: "/dashboard",      icon: LayoutDashboard, key: "dashboard",      badge: null,  adminOnly: false },
  { path: "/profil",         icon: User,            key: "profil",         badge: null,  adminOnly: false },
  { path: "/parametres",     icon: Settings,        key: "parametres",     badge: null,  adminOnly: false },
  { path: "/abonnement",     icon: CreditCard,      key: "abonnement",     badge: null,  adminOnly: false },
  { path: "/admin",          icon: Shield,          key: "admin",          badge: "ADM", adminOnly: true  },
];

export const Sidebar = () => {
  const { t } = useTranslation();
  const collapsed           = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar       = useUIStore((s) => s.toggleSidebar);
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed);
  const theme               = useUIStore((s) => s.theme);
  const toggleTheme         = useUIStore((s) => s.toggleTheme);
  const { logout, user }    = useAuthStore();
  const { profil }          = useProfilStore();
  const navigate            = useNavigate();
  const isAdmin = ["admin", "super_admin", "yukpo_owner"].includes(user?.role || "");
  const isDark = theme === "dark";

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
        collapsed ? "w-16" : "w-64"
      )}
      style={{
        background: "linear-gradient(180deg, var(--ykp-sidebar-start) 0%, var(--ykp-sidebar-end) 100%)",
        borderRight: "1px solid var(--ykp-sidebar-border)",
      }}
    >
      {/* Filet supérieur — gradient corporate (inchangé : identité de marque) */}
      <div
        className="h-0.5 w-full flex-shrink-0"
        style={{ background: "linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)" }}
        aria-hidden="true"
      />

      {/* Logo */}
      <div
        className={cn(
          "flex items-center h-14 flex-shrink-0",
          collapsed ? "justify-center px-2" : "px-4"
        )}
        style={{ borderBottom: "1px solid var(--ykp-sidebar-border)" }}
      >
        {collapsed ? (
          <div style={{
            width: 40, height: 40, background: "white", borderRadius: 10,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 2,
            boxShadow: "0 0 0 1px rgba(255,255,255,0.15), 0 2px 6px rgba(0,0,0,0.25)",
          }}>
            <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
        ) : (
          <YukpoLogo size={30} />
        )}
      </div>

      {/* Profil utilisateur */}
      {!collapsed && (
        <div
          className="mx-3 my-2.5 p-3 rounded-xl"
          style={{
            background: "var(--ykp-sidebar-profile-bg)",
            border: "1px solid var(--ykp-sidebar-profile-border)",
          }}
        >
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
              <p
                className="text-sm font-semibold truncate leading-tight"
                style={{ color: "var(--ykp-sidebar-active-text)" }}
              >
                {isAdmin ? "Administrateur" : (profil?.metier?.replace(/_/g, " ") || "Professionnel")}
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                {isAdmin ? (
                  <><Shield className="w-3 h-3 text-red-500" /><span className="text-xs text-red-500 font-medium">Accès total</span></>
                ) : (
                  <><Sparkles className="w-3 h-3 text-gold-500" /><span className="text-xs text-gold-600 dark:text-gold-400 font-medium">{profil?.niveau_pro || "Starter"}</span></>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 py-2 overflow-y-auto" aria-label="Navigation principale">
        <ul className="space-y-0.5 px-2">
          {NAV_KEYS.filter((item) => !item.adminOnly || isAdmin).map(({ path, icon: Icon, key, badge }) => {
            const label = t(`nav.${key}`);
            return (
              <li key={path}>
                <NavLink
                  to={path}
                  className={({ isActive }) => cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium",
                    "transition-all duration-150 group relative",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-yukpo-500 focus-visible:ring-offset-1",
                    isActive ? "sidebar-link-active" : "sidebar-link-idle"
                  )}
                  style={({ isActive }) => isActive ? {
                    background: "var(--ykp-sidebar-active-bg)",
                    borderLeft: "2px solid var(--ykp-sidebar-active-border)",
                    color: "var(--ykp-sidebar-active-text)",
                    boxShadow: isDark ? "inset 0 0 0 1px rgba(0,176,240,0.12)" : "inset 0 0 0 1px rgba(99,102,241,0.08)",
                  } : {
                    color: "var(--ykp-sidebar-text-muted)",
                  }}
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={cn("w-4 h-4 flex-shrink-0 transition-colors")}
                        style={{ color: isActive ? "#00B0F0" : "var(--ykp-sidebar-text-muted)" }}
                      />
                      {!collapsed && (
                        <>
                          <span className="flex-1 truncate">{label}</span>
                          {badge && (
                            <span style={{
                              fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
                              padding: "2px 7px", borderRadius: 999,
                              background: badge === "ADM" ? "rgba(239,68,68,0.22)" : badge === "NEW" ? "rgba(0,176,240,0.22)" : "rgba(0,84,166,0.28)",
                              color: badge === "ADM" ? "#fca5a5" : "#00B0F0",
                              border: `1px solid ${badge === "ADM" ? "rgba(239,68,68,0.35)" : "rgba(0,176,240,0.35)"}`,
                            }}>{badge}</span>
                          )}
                        </>
                      )}
                      {collapsed && (
                        <div
                          className="absolute left-full ml-3 px-3 py-1.5 text-xs rounded-lg opacity-0 group-hover:opacity-100 whitespace-nowrap z-50 pointer-events-none transition-opacity duration-150"
                          style={{
                            background: "var(--ykp-sidebar-tooltip-bg)",
                            color: "var(--ykp-sidebar-tooltip-text)",
                            border: "1px solid var(--ykp-sidebar-tooltip-border)",
                            boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
                          }}
                        >
                          {label}
                          {badge && <span className="ml-2 font-semibold" style={{ color: "#00B0F0" }}>{badge}</span>}
                        </div>
                      )}
                    </>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Diviseur graphique */}
      {!collapsed && (
        <div
          className="mx-4 my-1 h-px"
          style={{
            background: "linear-gradient(90deg, transparent, rgba(0,176,240,0.35), transparent)",
          }}
          aria-hidden="true"
        />
      )}

      {/* Footer */}
      <div className="p-2 flex-shrink-0">
        {/* Section label Paramètres */}
        {!collapsed && (
          <p className="px-2 pt-1 pb-1 text-[10px] font-semibold uppercase tracking-widest"
             style={{ color: "var(--ykp-sidebar-text-muted)", opacity: 0.6 }}>
            {t("settings.label", "Paramètres")}
          </p>
        )}
        <div className="space-y-0.5">
        {/* Language switcher */}
        <LanguageSwitcher collapsed={collapsed} />

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs transition-all"
          style={{ color: "var(--ykp-sidebar-text-muted)", background: "transparent" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--ykp-sidebar-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          title={t("theme.toggle")}
        >
          {isDark ? <Sun className="w-4 h-4 flex-shrink-0" /> : <Moon className="w-4 h-4 flex-shrink-0" />}
          {!collapsed && <span>{isDark ? t("theme.light") : t("theme.dark")}</span>}
        </button>

        <button
          onClick={toggleSidebar}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs transition-all"
          style={{ color: "var(--ykp-sidebar-text-muted)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--ykp-sidebar-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          {collapsed
            ? <ChevronRight className="w-4 h-4 mx-auto" />
            : <><ChevronLeft className="w-4 h-4" /><span>{t("nav.collapseMenu")}</span></>}
        </button>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs transition-all"
          style={{ color: "var(--ykp-sidebar-text-muted)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(153,27,27,0.18)";
            e.currentTarget.style.color = "#fca5a5";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--ykp-sidebar-text-muted)";
          }}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>{t("nav.logout")}</span>}
        </button>
        </div>{/* end space-y-0.5 */}
      </div>{/* end footer */}
    </aside>
  );
};
