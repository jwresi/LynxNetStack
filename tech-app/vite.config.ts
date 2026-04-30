import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3020,
    proxy: {
      '/api/prov':  { target: 'http://localhost:5001', changeOrigin: true, rewrite: p => p.replace(/^\/api\/prov/, '') },
      '/api/jake':  { target: 'http://localhost:8080', changeOrigin: true, rewrite: p => p.replace(/^\/api\/jake/, '') },
      '/api/tikfig':{ target: 'http://localhost:8082', changeOrigin: true, rewrite: p => p.replace(/^\/api\/tikfig/, '') },
    }
  }
})
