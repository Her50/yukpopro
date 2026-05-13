import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['logo.png', 'icons/*.png'],
      manifest: {
        name: 'YukpoSecrétariat — IA pour secrétaires africains',
        short_name: 'YukpoSec',
        description:
          'Rédaction IA, OCR, audio, traduction, infographie, kanban, devis, caisse — tout pour les secrétaires et infographistes francophones.',
        theme_color: '#1d4ed8',
        background_color: '#1d4ed8',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        // Icônes "any" uniquement : les PNG du logo sont full-bleed
        // sans safe-zone, donc on ne les marque pas "maskable" pour
        // éviter qu'Android les rende bord-à-bord.
        icons: [
          { src: '/icons/icon-72x72.png',   sizes: '72x72',   type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-96x96.png',   sizes: '96x96',   type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-128x128.png', sizes: '128x128', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-144x144.png', sizes: '144x144', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-152x152.png', sizes: '152x152', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-384x384.png', sizes: '384x384', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        ],
        categories: ['business', 'productivity'],
        lang: 'fr',
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        navigateFallback: '/index.html',
        // Les appels API ne doivent jamais être servis depuis le cache.
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: /^\/api\/.*/,
            handler: 'NetworkOnly',
          },
        ],
        // Force l'activation immédiate du nouveau SW + prise de contrôle
        // des onglets ouverts. Sans ça, autoUpdate télécharge le nouveau
        // bundle mais l'utilisateur continue de voir l'ancien menu jusqu'à
        // ce que TOUS ses onglets soient fermés. Critique pour propager les
        // suppressions d'items de menu (Yukpo Studio, /traduction, etc.).
        // Cf. fix identique appliqué côté yukpopro_web (commit 2ea30b6b).
        skipWaiting: true,
        clientsClaim: true,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@yukpo/admin-dashboard': path.resolve(__dirname, '../packages/admin-dashboard/src'),
      '@yukpo/leads-dashboard': path.resolve(__dirname, '../packages/leads-dashboard/src'),
    },
    // packages/admin-dashboard a lucide-react/react/axios en peerDependencies
    // sans installation locale. dedupe force Vite/Rollup à résoudre depuis le
    // node_modules du root (yukposecretariat_web), évitant l'erreur :
    //   "Rollup failed to resolve import 'lucide-react' from packages/...".
    dedupe: ['react', 'react-dom', 'lucide-react', 'axios', 'zustand'],
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
