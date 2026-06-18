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
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
