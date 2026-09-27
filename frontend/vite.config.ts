import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
// Tailwind removed — using plain CSS with CSS custom properties

export default defineConfig({
  plugins: [
    react(),
    // Only enable PWA in production builds to avoid service worker caching during dev
    ...(process.env.NODE_ENV === 'production'
      ? [
          VitePWA({
            registerType: 'autoUpdate',
            manifest: {
              name: 'CUA-Sentinel',
              short_name: 'Sentinel',
              description: 'Personal 24/7 AI Dashboard',
              theme_color: '#0f0f0f',
              background_color: '#0f0f0f',
              display: 'standalone',
              icons: [
                { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml' },
              ],
            },
            workbox: { globPatterns: ['**/*.{js,css,html,ico,png,svg}'] },
          }),
        ]
      : []),
  ],
  server: {
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true, configure: (proxy) => { proxy.on('error', () => {}) } },
    },
  },
})
