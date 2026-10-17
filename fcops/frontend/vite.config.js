import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // One origin in dev: the browser only ever talks to Vite, which forwards
    // API and admin calls. changeOrigin stays false so Django sees the
    // browser's Host and CSRF origin checks pass without trusted origins.
    proxy: Object.fromEntries(['/api', '/api-auth', '/admin', '/static'].map((prefix) => [
      prefix, { target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: false },
    ])),
  },
})
