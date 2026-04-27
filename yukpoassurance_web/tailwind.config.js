/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        assurance: {
          50:  "#e8f0fa",
          100: "#c5d8f4",
          200: "#8db3e9",
          300: "#558ede",
          400: "#2b6fc9",
          500: "#0054A6",
          600: "#004490",
          700: "#003370",
          800: "#002354",
          900: "#001438",
          950: "#000b20",
        },
        ciel: {
          50:  "#e6f9ff",
          100: "#b3efff",
          400: "#33ccff",
          500: "#00B0F0",
          600: "#008fcc",
        },
        alerte: {
          400: "#fb923c",
          500: "#f97316",
          600: "#ea580c",
        },
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
      },
      keyframes: {
        fadeIn:    { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp:   { "0%": { opacity: "0", transform: "translateY(20px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        slideRight:{ "0%": { opacity: "0", transform: "translateX(-20px)" }, "100%": { opacity: "1", transform: "translateX(0)" } },
      },
      backgroundImage: {
        "assurance-gradient": "linear-gradient(135deg, #0054A6 0%, #0079D4 50%, #00B0F0 100%)",
        "dark-gradient":      "linear-gradient(180deg, #111827 0%, #0D1117 100%)",
        "card-glow":          "linear-gradient(135deg, rgba(0,84,166,0.08) 0%, rgba(0,176,240,0.04) 100%)",
        "cima-band":          "linear-gradient(90deg, #0054A6, #00B0F0, #0054A6)",
      },
      boxShadow: {
        "assurance":    "0 0 30px rgba(0,84,166,0.25)",
        "assurance-lg": "0 0 60px rgba(0,84,166,0.35)",
        "card":     "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05)",
        "card-lg":  "0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
