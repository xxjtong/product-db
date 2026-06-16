/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  base: '/product-db/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/product-db/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/product-db/hermes': {
        target: 'http://127.0.0.1:8642',
        rewrite: (path) => path.replace(/^\/product-db\/hermes/, ''),
        configure: (proxy) => {
          const apiKey = process.env.VITE_HERMES_API_KEY || 'qs-65bf75614bdd4245'
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Authorization', `Bearer ${apiKey}`)
            proxyReq.removeHeader('Origin')
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
    },
  },
  resolve: {
    dedupe: ['react', 'react-dom', '@wendellhu/redi', 'rxjs'],
  },
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'rxjs',
      '@wendellhu/redi',
    ],
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
