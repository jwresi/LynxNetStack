import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3020,
    proxy: {
      // Provisioner Flask — CPE scan and onboarding
      '/api/prov': {
        target: 'http://localhost:5001',
        changeOrigin: true,
        rewrite: p => p.replace(/^\/api\/prov/, ''),
      },
      // Jake2 API server — subscriber lookup, network queries
      // WHY: Jake2 runs on :8017 (configured in api/jake_api_server.py).
      // Do not use :8080 — that is the old Jake port.
      '/api/jake': {
        target: 'http://localhost:8017',
        changeOrigin: true,
        rewrite: p => p.replace(/^\/api\/jake/, '/api'),
      },
      // Tikfig — config generation
      '/api/tikfig': {
        target: 'http://localhost:8082',
        changeOrigin: true,
        rewrite: p => p.replace(/^\/api\/tikfig/, ''),
      },
    }
  }
})
