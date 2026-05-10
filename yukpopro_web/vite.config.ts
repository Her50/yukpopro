import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "logo.png", "icons/*.png"],
      manifest: {
        name: "YukpoPro — Intelligence Professionnelle Africaine",
        short_name: "YukpoPro",
        description: "L'Assistant IA des Professionnels Africains",
        theme_color: "#7B3FE4",
        background_color: "#020617",
        display: "standalone",
        orientation: "portrait",
        scope: "/",
        start_url: "/",
        // Note : on n'inclut QUE des icônes "any". Les icônes "maskable" exigent
        // une safe-zone (logo dans les 80% centraux + padding coloré autour).
        // Réutiliser les PNG full-bleed avec purpose:"maskable" force Android à
        // les rendre bord-à-bord → l'icône paraît exagérément grande sur l'écran
        // d'accueil. À ré-activer uniquement si on génère des PNG dédiés safe-zone.
        icons: [
          { src: "/icons/icon-72x72.png",   sizes: "72x72",   type: "image/png", purpose: "any" },
          { src: "/icons/icon-96x96.png",   sizes: "96x96",   type: "image/png", purpose: "any" },
          { src: "/icons/icon-128x128.png", sizes: "128x128", type: "image/png", purpose: "any" },
          { src: "/icons/icon-144x144.png", sizes: "144x144", type: "image/png", purpose: "any" },
          { src: "/icons/icon-152x152.png", sizes: "152x152", type: "image/png", purpose: "any" },
          { src: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icons/icon-384x384.png", sizes: "384x384", type: "image/png", purpose: "any" },
          { src: "/icons/icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "any" },
        ],
        categories: ["business", "productivity"],
        lang: "fr",
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        navigateFallback: "/index.html",
        // Force activation immédiate du nouveau SW + prise de contrôle des
        // onglets ouverts. Sans ça, autoUpdate télécharge le nouveau bundle
        // mais l'utilisateur continue de voir l'ancien menu jusqu'à ce que
        // TOUS ses onglets soient fermés. Critique pour propager les
        // suppressions d'items de menu (Yukpo Studio, /traduction, etc.).
        skipWaiting: true,
        clientsClaim: true,
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@yukpo/admin-dashboard": path.resolve(__dirname, "../packages/admin-dashboard/src"),
    },
    // packages/admin-dashboard a lucide-react/react/axios en peerDependencies
    // sans installation locale. dedupe force Vite/Rollup à résoudre depuis le
    // node_modules du root (yukpopro_web), évitant l'erreur :
    //   "Rollup failed to resolve import 'lucide-react' from packages/...".
    dedupe: ["react", "react-dom", "lucide-react", "axios"],
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom", "react-router-dom"],
          "query": ["@tanstack/react-query"],
          "charts": ["recharts"],
          "motion": ["framer-motion"],
          "i18n": ["i18next", "react-i18next", "i18next-browser-languagedetector"],
          "markdown": ["react-markdown", "remark-gfm"],
          "icons": ["lucide-react"],
          "utils": ["axios", "date-fns", "clsx", "tailwind-merge", "zustand"],
        },
      },
    },
  },
});
