import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { env } from 'node:process'

const apiProxy = { '/api': env.VITE_API_TARGET || 'http://127.0.0.1:5001' }

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: apiProxy,
  },
  preview: { host: '127.0.0.1', proxy: apiProxy },
  test: { environment: 'jsdom', setupFiles: ['./src/testSetup.js'], css: false, maxWorkers: 2, testTimeout: 15000 },
})
