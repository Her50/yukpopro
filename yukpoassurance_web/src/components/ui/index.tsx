import { type ClassValue, clsx as clsxBase } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsxBase(inputs));
}

// ── Logo ──────────────────────────────────────────────────────────────────────

interface LogoProps { size?: number; collapsed?: boolean }

export function AssuranceLogo({ size = 28, collapsed = false }: LogoProps) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        style={{
          width: size + 8, height: size + 8,
          background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)",
          borderRadius: 10,
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 0 12px rgba(0,84,166,0.4)",
          flexShrink: 0,
        }}
      >
        <svg width={size - 2} height={size - 2} viewBox="0 0 24 24" fill="none">
          <path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.35C17.25 22.15 21 17.25 21 12V7L12 2z"
            fill="white" opacity="0.9" />
          <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {!collapsed && (
        <div>
          <span style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", fontWeight: 700, fontSize: 15, color: "white", letterSpacing: "-0.02em" }}>
            Yukpo
          </span>
          <span style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", fontWeight: 700, fontSize: 15, color: "#00B0F0", letterSpacing: "-0.02em" }}>
            Assurance
          </span>
        </div>
      )}
    </div>
  );
}

// ── Badge ─────────────────────────────────────────────────────────────────────

interface BadgeProps {
  children: React.ReactNode;
  variant?: "blue" | "orange" | "green" | "red" | "gray";
  size?: "sm" | "xs";
}

const BADGE_VARIANTS = {
  blue:   "bg-assurance-500/20 text-ciel-400 border-assurance-500/30",
  orange: "bg-alerte-500/20 text-alerte-400 border-alerte-500/30",
  green:  "bg-green-500/20 text-green-400 border-green-500/30",
  red:    "bg-red-500/20 text-red-400 border-red-500/30",
  gray:   "bg-white/10 text-gray-400 border-white/10",
};

export function Badge({ children, variant = "blue", size = "sm" }: BadgeProps) {
  return (
    <span className={cn(
      "inline-flex items-center rounded-full border font-semibold leading-none",
      size === "sm" ? "px-2 py-0.5 text-xs" : "px-1.5 py-0.5 text-[10px]",
      BADGE_VARIANTS[variant]
    )}>
      {children}
    </span>
  );
}

// ── Spinner ───────────────────────────────────────────────────────────────────

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={cn("animate-spin text-ciel-400", className)} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.37 0 0 5.37 0 12h4z" />
    </svg>
  );
}

// ── formatMontant ─────────────────────────────────────────────────────────────

export function formatMontant(n?: number): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("fr-FR").format(n) + " FCFA";
}
