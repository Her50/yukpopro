/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    // Composants Tailwind partagés (admin-dashboard cross-app) — sans ça
    // Tailwind ne scanne pas les classes du package → CSS non généré →
    // tous les onglets/boutons admin invisibles en prod.
    "../packages/admin-dashboard/src/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // ── Marque Yukpo — corporate navy (sidebar, header) ────────────────
        navy: {
          700: "#2a3657",
          800: "#243050",
          900: "#1e2640",   // DS sidebar top
          950: "#162033",   // DS sidebar bottom
        },
        // ── Couleur corporate — bleu institutionnel Yukpo ──────────────────
        corp: {
          300: "#60a5fa",
          400: "#3b82f6",
          500: "#0083d6",
          600: "#0054A6",   // DS Yukpo Deep — CTA primaire
          700: "#003476",   // DS Yukpo Dark — hover/pressed
          800: "#002258",
        },
        // ── Bright accent (highlights, liens, badges) ──────────────────────
        bright: {
          300: "#67d8f5",
          400: "#00B0F0",   // DS Yukpo Bright
          500: "#0094CC",
        },
        // ── YukpoPro — accent indigo (différentiateur produit) ─────────────
        yukpo: {
          50:  "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",   // Indigo — accentuation YukpoPro
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        // ── Neutrals (echelle claire → foncée) ───────────────────────────
        neutral: {
          50:  "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
        // ── Accent cyan ────────────────────────────────────────────────────
        accent: {
          50:  "#ecfeff",
          100: "#cffafe",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
        },
        // ── Gold (XP, crédits) ─────────────────────────────────────────────
        gold: {
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
        },
        // ── Sémantiques ───────────────────────────────────────────────────
        success: { 400: "#34d399", 500: "#10b981", 600: "#059669" },
        warning: { 400: "#fbbf24", 500: "#f59e0b", 600: "#d97706" },
        danger:  { 400: "#f87171", 500: "#ef4444", 600: "#dc2626" },
        // ── Dark palette (héritage — à ne plus utiliser pour nouveaux écrans)
        dark: {
          50:  "#F9FAFB",
          100: "#F3F4F6",
          200: "#E5E7EB",
          300: "#D1D5DB",
          400: "#9CA3AF",
          500: "#6B7280",
          600: "#4B5563",
          700: "#374151",
          800: "#1F2937",
          850: "#192330",
          900: "#111827",
          950: "#0D1117",
        },
      },
      fontFamily: {
        sans:    ["Inter", "system-ui", "sans-serif"],
        display: ["Plus Jakarta Sans", "Inter", "sans-serif"],
        mono:    ["JetBrains Mono", "Fira Code", "monospace"],
      },
      animation: {
        "fade-in":    "fadeIn 0.3s ease-out",
        "slide-up":   "slideUp 0.4s ease-out",
        "slide-right":"slideRight 0.3s ease-out",
        "pulse-slow": "pulse 3s ease-in-out infinite",
        "typing":     "typing 1.2s steps(3) infinite",
      },
      keyframes: {
        fadeIn:    { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp:   { "0%": { opacity: "0", transform: "translateY(20px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        slideRight:{ "0%": { opacity: "0", transform: "translateX(-20px)" }, "100%": { opacity: "1", transform: "translateX(0)" } },
        typing:    { "0%,100%": { content: "'...'" }, "33%": { content: "'..'" }, "66%": { content: "'.'" } },
      },
      backgroundImage: {
        // DS gradients signature
        "sidebar-gradient": "linear-gradient(180deg, #1e2640 0%, #162033 100%)",
        "header-gradient":  "linear-gradient(90deg, #0054A6 0%, #003476 50%, #1e2640 100%)",
        "divider-gradient": "linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)",
        "avatar-gradient":  "linear-gradient(135deg, #00B0F0, #0054A6)",
        // YukpoPro accent
        "yukpo-gradient":   "linear-gradient(135deg, #4f46e5 0%, #6366f1 50%, #818cf8 100%)",
        "pro-gradient":     "linear-gradient(135deg, #0054A6 0%, #4f46e5 100%)",
        "dark-gradient":    "linear-gradient(180deg, #1e2640 0%, #162033 100%)",
        "card-glow":        "linear-gradient(135deg, rgba(79,70,229,0.06) 0%, rgba(0,84,166,0.04) 100%)",
      },
      boxShadow: {
        "corp":     "0 0 24px rgba(0,84,166,0.3)",
        "corp-lg":  "0 0 48px rgba(0,84,166,0.4)",
        "yukpo":    "0 0 24px rgba(99,102,241,0.25)",
        "yukpo-lg": "0 0 48px rgba(99,102,241,0.35)",
        "card":     "0 1px 3px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.04)",
        "card-lg":  "0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)",
        "nav-active":"inset 0 0 0 1px rgba(99,102,241,0.3), 0 0 12px rgba(99,102,241,0.15)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
