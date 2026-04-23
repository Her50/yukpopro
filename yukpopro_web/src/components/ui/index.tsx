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
    "focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-navy-950",
    "disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]",
  ].join(" ");

  const variants = {
    // Bleu corporate — CTA primaire DS
    primary:   "bg-corp-600 hover:bg-corp-700 text-white focus-visible:ring-corp-500 shadow-md shadow-corp-600/30",
    // Secondaire — gris clair en light, white/subtle en dark
    secondary: "bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 dark:bg-white/[0.07] dark:hover:bg-white/[0.12] dark:text-slate-200 dark:border-white/[0.10] focus-visible:ring-slate-400",
    // Ghost — actions tertiaires
    ghost:     "bg-transparent hover:bg-slate-100 text-slate-600 hover:text-slate-900 dark:hover:bg-white/[0.06] dark:text-slate-400 dark:hover:text-slate-100 focus-visible:ring-slate-400",
    // Danger / destructif
    danger:    "bg-danger-500 hover:bg-danger-600 text-white focus-visible:ring-danger-400",
    // Gold — crédits / premium
    gold:      "bg-gold-500 hover:bg-gold-600 text-slate-900 dark:text-navy-950 font-bold focus-visible:ring-gold-400 shadow-md shadow-gold-500/20",
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
        <label
          className="text-xs font-semibold tracking-wide uppercase"
          style={{ color: "var(--ykp-text-secondary)" }}
        >
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <div
            className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: "var(--ykp-text-faint)" }}
          >
            {icon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full rounded-lg",
            "px-4 py-2.5 text-sm transition-colors duration-150",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60 focus-visible:ring-offset-1",
            icon && "pl-10",
            className
          )}
          style={{
            background: "var(--ykp-input-bg)",
            border: `1px solid ${error ? "#ef4444" : "var(--ykp-input-border)"}`,
            color: "var(--ykp-text-primary)",
          }}
          {...props}
        />
      </div>
      {error && <p className="text-xs text-danger-500">{error}</p>}
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
        <label
          className="text-xs font-semibold tracking-wide uppercase"
          style={{ color: "var(--ykp-text-secondary)" }}
        >
          {label}
        </label>
      )}
      <select
        ref={ref}
        className={cn(
          "w-full rounded-lg",
          "px-4 py-2.5 text-sm transition-colors duration-150",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60",
          className
        )}
        style={{
          background: "var(--ykp-input-bg)",
          border: `1px solid ${error ? "#ef4444" : "var(--ykp-input-border)"}`,
          color: "var(--ykp-text-primary)",
        }}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-danger-500">{error}</p>}
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
        <label
          className="text-xs font-semibold tracking-wide uppercase"
          style={{ color: "var(--ykp-text-secondary)" }}
        >
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-lg",
          "px-4 py-3 text-sm resize-none transition-colors duration-150",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-corp-500/60",
          className
        )}
        style={{
          background: "var(--ykp-input-bg)",
          border: `1px solid ${error ? "#ef4444" : "var(--ykp-input-border)"}`,
          color: "var(--ykp-text-primary)",
        }}
        {...props}
      />
      {error && <p className="text-xs text-danger-500">{error}</p>}
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
      background: "var(--ykp-surface-gradient)",
      border: "1px solid var(--ykp-border)",
      boxShadow: "var(--ykp-shadow-card)",
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
    corp:   "bg-corp-600/15 text-corp-700 border-corp-600/25 dark:bg-corp-600/20 dark:text-bright-400 dark:border-corp-600/30",
    purple: "bg-yukpo-500/15 text-yukpo-700 border-yukpo-500/25 dark:bg-yukpo-500/20 dark:text-yukpo-300 dark:border-yukpo-500/30",
    cyan:   "bg-accent-500/15 text-accent-700 border-accent-500/25 dark:bg-accent-500/20 dark:text-accent-400 dark:border-accent-500/30",
    gold:   "bg-gold-500/15 text-gold-700 border-gold-500/25 dark:bg-gold-500/20 dark:text-gold-400 dark:border-gold-500/30",
    green:  "bg-success-500/15 text-success-700 border-success-500/25 dark:bg-success-500/20 dark:text-success-400 dark:border-success-500/30",
    red:    "bg-danger-500/15 text-danger-700 border-danger-500/25 dark:bg-danger-500/20 dark:text-danger-400 dark:border-danger-500/30",
    slate:  "bg-slate-100 text-slate-700 border-slate-200 dark:bg-white/[0.07] dark:text-slate-300 dark:border-white/[0.10]",
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
    <svg className={cn("animate-spin text-corp-600 dark:text-corp-400", sizes[size])} fill="none" viewBox="0 0 24 24">
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
        <span
          className="font-display font-bold tracking-tight"
          style={{ fontSize: size * 0.56, color: "var(--ykp-sidebar-active-text)" }}
        >
          Yukpo<span style={{ color: "#00B0F0" }}>Pro</span>
        </span>
        <span
          className="tracking-wide"
          style={{ fontSize: size * 0.24, color: "var(--ykp-sidebar-text-muted)" }}
        >
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
  <div
    className="flex items-start justify-between px-6 py-5"
    style={{ borderBottom: "1px solid var(--ykp-border)" }}
  >
    <div className="flex items-center gap-3">
      {Icon && (
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{
            background: "linear-gradient(135deg, rgba(0,84,166,0.12), rgba(99,102,241,0.10))",
            border: "1px solid rgba(0,176,240,0.20)",
          }}
        >
          <Icon className="w-5 h-5 text-corp-600 dark:text-bright-400" />
        </div>
      )}
      <div>
        <h1
          className="text-lg font-bold leading-tight"
          style={{ color: "var(--ykp-text-primary)" }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            className="text-xs mt-0.5"
            style={{ color: "var(--ykp-text-muted)" }}
          >
            {subtitle}
          </p>
        )}
      </div>
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
);
