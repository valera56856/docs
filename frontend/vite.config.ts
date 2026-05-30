/**
 * Vite configuration for the Valeraup PWA.
 *
 * - React plugin enables the modern JSX runtime + fast refresh.
 * - `vite-plugin-pwa` registers a service worker and emits the web app manifest
 *   so the app is installable on a phone home screen (the primary delivery
 *   surface — managers photograph invoices on mobile).
 * - The `@` alias mirrors the `paths` entry in tsconfig.json.
 *
 * The PWA `manifest` here is the source of truth Vite injects into the build.
 * `public/manifest.webmanifest` is kept as a static fallback / reference; both
 * must stay in sync (name, theme color, icon paths).
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['robots.txt', 'icons/icon-192.png', 'icons/icon-512.png'],
      manifest: {
        name: 'Valeraup',
        short_name: 'Valeraup',
        description:
          'Photograph a supplier invoice, recognize line items, map SKUs, generate an Excel receipt for SalesDrive.',
        // NextCRM navy — keeps the install splash / status bar on-brand.
        theme_color: '#0A1A3F',
        background_color: '#0A1A3F',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        icons: [
          {
            src: '/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any maskable',
          },
          {
            src: '/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        // Precache the built app shell; runtime caching for API responses is
        // intentionally left out — invoice data must always be fresh.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
      },
      devOptions: {
        // Allow testing the service worker during `vite dev`.
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
  },
  preview: {
    port: 4173,
  },
});
