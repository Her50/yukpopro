/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    // Composants Tailwind partagés (admin-dashboard cross-app) — sans ça
    // Tailwind ne scanne pas les classes du package → CSS non généré →
    // tous les onglets/boutons admin invisibles en prod.
    '../packages/admin-dashboard/src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Mapping yukpo-* utilisé par le package admin-dashboard cross-app.
        // Sans ce mapping côté Sec, les boutons/onglets admin n'ont pas de
        // couleur (le package est partagé avec YPro qui définit yukpo).
        yukpo: {
          50:  '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
        },
        brand: {
          50:  '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        accent: {
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
