import { type ReactNode, type ButtonHTMLAttributes, type InputHTMLAttributes, forwardRef } from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...args: Parameters<typeof clsx>) => twMerge(clsx(...args));

// ── Button ────────────────────────────────────────────────────────────────────

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "gold";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

export const Button = ({
  variant = "primary", size = "md", loading, icon, children, className, disabled, ...props
}: ButtonProps) => {
  const base = [
    "inline-flex items-center justify-center gap-2 font-semibold rounded-lg",
    "transition-all duration-150 focus:outline-none focus-visible:ring-2",
    "focus-visible:ring-offset-2 focus-visible:ring-offset-navy-950",
    "disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]",
  ].join(" ");

  const variants = {
    // Bleu corporate — CTA primaire DS
    primary:   "bg-corp-600 hover:bg-corp-700 text-white focus-visible:ring-corp-500 shadow-md shadow-corp-600/30",
    // Surfaces navbar / secondaire
    secondary: "bg-white/[0.07] hover:bg-white/[0.12] text-slate-200 border border-white/[0.10] focus-visible:ring-slate-500",
    // Ghost — actions tertiaires
    ghost:     "bg-transparent hover:bg-white/[0.06] text-slate-400 hover:text-slate-100 focus-visible:ring-slate-500",
    // Danger / destructif
    danger:    "bg-danger-500 hover:bg-danger-600 text-white focus-visible:ring-danger-400",
    // Gold — crédits / premium
    gold:      "bg-gold-500 hover:bg-gold-600 text-navy-950 font-bold focus-visible:ring-gold-400 shadow-md shadow-gold-500/20",
  };

  const sizes = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2.5 text-sm",
    lg: "px-6 py-3 text-base",
  };

  return (
    <button className={cn(base, variants[variant], sizes[size], className)} disabled={disabled || loading} {...props}>
      {loading ? (
        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : icon}
      {children}
    </button>
  );
};

// ── Input ─────────────────────────────────────────────────────────────────────

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, className, ...props }, ref) => (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-semibold text-slate-300 tracking-wide uppercase">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full rounded-lg text-slate-100 placeholder-slate-600",
            "px-4 py-2.5 text-sm transition-colors duration-150",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60 focus-visible:ring-offset-1 focus-visible:ring-offset-navy-900",
            icon && "pl-10",
            error ? "border-danger-500 focus-visible:ring-danger-400" : "border-white/[0.10]",
            className
          )}
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.09)" }}
          {...props}
        />
      </div>
      {error && <p className="text-xs text-danger-400">{error}</p>}
    </div>
  )
);
Input.displayName = "Input";

// ── Select ────────────────────────────────────────────────────────────────────

interface SelectProps extends InputHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, options, error, className, ...props }, ref) => (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-semibold text-slate-300 tracking-wide uppercase">
          {label}
        </label>
      )}
      <select
        ref={ref}
        className={cn(
          "w-full rounded-lg text-slate-100",
          "px-4 py-2.5 text-sm transition-colors duration-150",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60",
          error && "border-danger-500",
          className
        )}
        style={{
          background: "#1e2640",
          border: "1px solid rgba(255,255,255,0.09)",
        }}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} style={{ background: "#1e2640" }}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-danger-400">{error}</p>}
    </div>
  )
);
Select.displayName = "Select";

// ── Textarea ──────────────────────────────────────────────────────────────────

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className, ...props }, ref) => (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-semibold text-slate-300 tracking-wide uppercase">
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-lg text-slate-100 placeholder-slate-600",
          "px-4 py-3 text-sm resize-none transition-colors duration-150",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60",
          error && "border-danger-500",
          className
        )}
        style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.09)" }}
        {...props}
      />
      {error && <p className="text-xs text-danger-400">{error}</p>}
    </div>
  )
);
Textarea.displayName = "Textarea";

// ── Card ──────────────────────────────────────────────────────────────────────

export const Card = ({
  children, className, style, ...props
}: { children: ReactNode; className?: string; style?: React.CSSProperties } & React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("rounded-xl", className)}
    style={{
      background: "linear-gradient(135deg, #243050 0%, #1e2640 100%)",
      border: "1px solid rgba(0,84,166,0.12)",
      boxShadow: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03)",
      ...style,
    }}
    {...props}
  >
    {children}
  </div>
);

// ── Badge ─────────────────────────────────────────────────────────────────────

interface BadgeProps {
  children: ReactNode;
  variant?: "corp" | "purple" | "cyan" | "gold" | "green" | "red" | "slate";
  size?: "sm" | "md";
}

export const Badge = ({ children, variant = "corp", size = "md" }: BadgeProps) => {
  const colors = {
    corp:   "bg-corp-600/20 text-bright-400 border-corp-600/30",
    purple: "bg-yukpo-500/20 text-yukpo-300 border-yukpo-500/30",
    cyan:   "bg-accent-500/20 text-accent-400 border-accent-500/30",
    gold:   "bg-gold-500/20 text-gold-400 border-gold-500/30",
    green:  "bg-success-500/20 text-success-400 border-success-500/30",
    red:    "bg-danger-500/20 text-danger-400 border-danger-500/30",
    slate:  "bg-white/[0.07] text-slate-300 border-white/[0.10]",
  };
  const sizes = { sm: "text-[10px] px-2 py-0.5", md: "text-xs px-2.5 py-1" };
  return (
    <span className={cn(
      "inline-flex items-center font-semibold rounded-full border tracking-wide",
      colors[variant], sizes[size]
    )}>
      {children}
    </span>
  );
};

// ── Spinner ───────────────────────────────────────────────────────────────────

export const Spinner = ({ size = "md" }: { size?: "sm" | "md" | "lg" }) => {
  const sizes = { sm: "w-4 h-4", md: "w-6 h-6", lg: "w-10 h-10" };
  return (
    <svg className={cn("animate-spin text-corp-400", sizes[size])} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
};

// ── YukpoPro Logo ─────────────────────────────────────────────────────────────

export const YukpoLogo = ({ size = 32, showText = true }: { size?: number; showText?: boolean }) => (
  <div className="flex items-center gap-3">
    <div style={{
      width: size * 1.35, height: size * 1.35, background: "white",
      borderRadius: size * 0.25, display: "flex", alignItems: "center",
      justifyContent: "center", padding: size * 0.12, flexShrink: 0,
      boxShadow: "0 0 0 1px rgba(0,84,166,0.35), 0 4px 12px rgba(0,84,166,0.2)",
    }}>
      <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
    </div>
    {showText && (
      <div className="flex flex-col leading-tight">
        <span className="font-display font-bold text-white tracking-tight" style={{ fontSize: size * 0.56 }}>
          Yukpo<span style={{ color: "#00B0F0" }}>Pro</span>
        </span>
        <span className="text-slate-500 tracking-wide" style={{ fontSize: size * 0.24 }}>
          Intelligence Africaine
        </span>
      </div>
    )}
  </div>
);

// ── Section header (helper pour titres de page) ───────────────────────────────

export const PageHeader = ({
  title, subtitle, actions, icon: Icon,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
}) => (
  <div className="flex items-start justify-between px-6 py-5 border-b border-white/[0.06]">
    <div className="flex items-center gap-3">
      {Icon && (
        <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: "linear-gradient(135deg, rgba(0,84,166,0.3), rgba(99,102,241,0.2))", border: "1px solid rgba(0,176,240,0.2)" }}>
          <Icon className="w-5 h-5 text-bright-400" />
        </div>
      )}
      <div>
        <h1 className="text-lg font-bold text-slate-100 leading-tight">{title}</h1>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
);
