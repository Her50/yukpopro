/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        yukpo: {
          50:  "#f3eeff",
          100: "#e2d5ff",
          200: "#c5aaff",
          300: "#a87fff",
          400: "#8b54ff",
          500: "#7B3FE4",
          600: "#6420cc",
          700: "#4e18a3",
          800: "#3a1278",
          900: "#250b4f",
          950: "#13062a",
        },
        accent: {
          50:  "#ecfeff",
          100: "#cffafe",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
        },
        gold: {
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
        },
        // Dark Pro — palette warm gray (Linear / GitHub Dark)
        dark: {
          50:  "#F9FAFB",
          100: "#F3F4F6",
          200: "#E5E7EB",
          300: "#D1D5DB",
          400: "#9CA3AF",
          500: "#6B7280",
          600: "#4B5563",
          700: "#374151",
          800: "#1F2937",   // cartes
          850: "#192330",   // cartes élevées
          900: "#111827",   // fond principal
          950: "#0D1117",   // sidebar
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
        "yukpo-gradient": "linear-gradient(135deg, #7B3FE4 0%, #4A90D9 50%, #06B6D4 100%)",
        "pro-gradient":   "linear-gradient(135deg, #7B3FE4 0%, #9B5FFF 100%)",
        "dark-gradient":  "linear-gradient(180deg, #111827 0%, #0D1117 100%)",
        "card-glow":      "linear-gradient(135deg, rgba(123,63,228,0.08) 0%, rgba(6,182,212,0.04) 100%)",
      },
      boxShadow: {
        "yukpo":    "0 0 30px rgba(123,63,228,0.25)",
        "yukpo-lg": "0 0 60px rgba(123,63,228,0.35)",
        "card":     "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05)",
        "card-lg":  "0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
