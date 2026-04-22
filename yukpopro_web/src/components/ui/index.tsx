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
  const base = "inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95";

  const variants = {
    primary:   "bg-yukpo-500 hover:bg-yukpo-600 text-white focus:ring-yukpo-500 shadow-lg shadow-yukpo-500/20",
    secondary: "bg-white/[0.06] hover:bg-white/[0.10] text-gray-200 border border-white/[0.10] focus:ring-gray-500",
    ghost:     "bg-transparent hover:bg-white/[0.06] text-gray-400 hover:text-gray-100 focus:ring-gray-500",
    danger:    "bg-red-600 hover:bg-red-700 text-white focus:ring-red-500",
    gold:      "bg-gold-500 hover:bg-gold-600 text-gray-900 focus:ring-gold-500 shadow-lg shadow-gold-500/20",
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
      {label && <label className="text-sm font-medium text-gray-300">{label}</label>}
      <div className="relative">
        {icon && <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">{icon}</div>}
        <input
          ref={ref}
          className={cn(
            "w-full bg-white/[0.06] border border-white/[0.10] rounded-xl text-gray-100 placeholder-gray-600",
            "px-4 py-2.5 text-sm transition-colors duration-200",
            "focus:outline-none focus:ring-2 focus:ring-yukpo-500/50 focus:border-yukpo-500/60",
            icon && "pl-10",
            error && "border-red-500 focus:ring-red-500",
            className
          )}
          {...props}
        />
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
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
      {label && <label className="text-sm font-medium text-gray-300">{label}</label>}
      <select
        ref={ref}
        className={cn(
          "w-full bg-[#1F2937] border border-white/[0.10] rounded-xl text-gray-100",
          "px-4 py-2.5 text-sm transition-colors duration-200",
          "focus:outline-none focus:ring-2 focus:ring-yukpo-500/50 focus:border-yukpo-500/60",
          error && "border-red-500",
          className
        )}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} style={{ background: "#1F2937" }}>{opt.label}</option>
        ))}
      </select>
      {error && <p className="text-xs text-red-400">{error}</p>}
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
      {label && <label className="text-sm font-medium text-gray-300">{label}</label>}
      <textarea
        ref={ref}
        className={cn(
          "w-full bg-white/[0.06] border border-white/[0.10] rounded-xl text-gray-100 placeholder-gray-600",
          "px-4 py-3 text-sm resize-none transition-colors duration-200",
          "focus:outline-none focus:ring-2 focus:ring-yukpo-500/50 focus:border-yukpo-500/60",
          error && "border-red-500",
          className
        )}
        {...props}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
);
Textarea.displayName = "Textarea";

// ── Card ──────────────────────────────────────────────────────────────────────

export const Card = ({
  children, className, ...props
}: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("rounded-2xl", className)}
    style={{
      background: "#1F2937",
      border: "1px solid rgba(255,255,255,0.07)",
      boxShadow: "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.03)",
    }}
    {...props}
  >
    {children}
  </div>
);

// ── Badge ─────────────────────────────────────────────────────────────────────

interface BadgeProps {
  children: ReactNode;
  variant?: "purple" | "cyan" | "gold" | "green" | "red" | "slate";
  size?: "sm" | "md";
}

export const Badge = ({ children, variant = "purple", size = "md" }: BadgeProps) => {
  const colors = {
    purple: "bg-yukpo-500/20 text-yukpo-300 border-yukpo-500/30",
    cyan:   "bg-accent-500/20 text-accent-400 border-accent-500/30",
    gold:   "bg-gold-500/20 text-gold-400 border-gold-500/30",
    green:  "bg-green-500/20 text-green-400 border-green-500/30",
    red:    "bg-red-500/20 text-red-400 border-red-500/30",
    slate:  "bg-white/[0.08] text-gray-300 border-white/[0.10]",
  };
  const sizes = { sm: "text-xs px-2 py-0.5", md: "text-xs px-2.5 py-1" };
  return (
    <span className={cn("inline-flex items-center font-medium rounded-full border", colors[variant], sizes[size])}>
      {children}
    </span>
  );
};

// ── Spinner ───────────────────────────────────────────────────────────────────

export const Spinner = ({ size = "md" }: { size?: "sm" | "md" | "lg" }) => {
  const sizes = { sm: "w-4 h-4", md: "w-6 h-6", lg: "w-10 h-10" };
  return (
    <svg className={cn("animate-spin text-yukpo-400", sizes[size])} fill="none" viewBox="0 0 24 24">
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
      borderRadius: size * 0.28, display: "flex", alignItems: "center",
      justifyContent: "center", padding: size * 0.12, flexShrink: 0,
      boxShadow: "0 0 0 1px rgba(123,63,228,0.3), 0 4px 16px rgba(123,63,228,0.25)",
    }}>
      <img src="/logo.png" alt="Yukpo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
    </div>
    {showText && (
      <div className="flex flex-col leading-none">
        <span className="font-display font-bold text-white tracking-tight" style={{ fontSize: size * 0.56 }}>
          Yukpo<span className="text-gold-400">Pro</span>
        </span>
        <span className="text-gray-500" style={{ fontSize: size * 0.24 }}>Intelligence Africaine</span>
      </div>
    )}
  </div>
);
