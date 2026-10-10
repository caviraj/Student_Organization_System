/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Listen on every interface: binding localhost alone makes 127.0.0.1 refuse and hides the LAN URL.
    host: true,
    // Fail loudly instead of quietly moving to 5174, which reads as "nothing is running".
    strictPort: true,
    proxy: {
      '/api': {
        // The backend binds 127.0.0.1, so name it that way: "localhost" can resolve to ::1.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
})
