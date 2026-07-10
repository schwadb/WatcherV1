import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'Territory Mapper',
        short_name: 'Territories',
        description: 'Territory & pin mapping for the US — works offline.',
        theme_color: '#1a73e8',
        background_color: '#f6f7f9',
        display: 'standalone',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // app shell + bundled boundary/population data precached
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}', 'data/*.json'],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        runtimeCaching: [
          {
            // style JSON, glyphs, sprites — cache-first so the basemap style loads offline
            urlPattern: /^https:\/\/tiles\.openfreemap\.org\/(styles|fonts|sprites|natural_earth)/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'basemap-assets',
              expiration: { maxEntries: 400, maxAgeSeconds: 60 * 60 * 24 * 90 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
});
