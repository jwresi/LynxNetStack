import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const NB_TOKEN = '8fd77834b1412f49a09e768be1b379f5416f33c3'

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
      // Jake2 API server
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
      // NetBox — token injected server-side so it's never in browser JS
      '/api/netbox': {
        target: 'http://172.27.48.233:8001',
        changeOrigin: true,
        rewrite: p => p.replace(/^\/api\/netbox/, ''),
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Authorization', `Token ${NB_TOKEN}`)
            proxyReq.setHeader('Accept', 'application/json')
          })
        },
      },
    }
  }
})
