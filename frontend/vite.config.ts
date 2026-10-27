import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const productionCsp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://coursesphere-8bd9a-default-rtdb.firebaseio.com wss://coursesphere-8bd9a-default-rtdb.firebaseio.com; frame-src https://coursesphere-8bd9a.firebaseapp.com; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
const developmentCsp = productionCsp
  .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
  .replace("connect-src 'self'", "connect-src 'self' http://127.0.0.1:9099 http://127.0.0.1:9000 ws://127.0.0.1:9000 ws://127.0.0.1:5173 ws://localhost:5173")
  .replace('frame-src ', 'frame-src http://127.0.0.1:9099 ')

const securityHeaders = (development: boolean) => ({
  'Content-Security-Policy': development ? developmentCsp : productionCsp,
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
})

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    headers: securityHeaders(true),
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    headers: securityHeaders(false),
  },
})
