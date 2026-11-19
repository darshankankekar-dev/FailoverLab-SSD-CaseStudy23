import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 1. Controller Traffic Telemetry APIs & Controller SSE Stream (Port 8000)
      '/api/v1/traffic/summary': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/v1/traffic/timeseries': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/v1/traffic/regions': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/v1/traffic/recent-events': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/v1/traffic/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },

      // 2. Gateway Traffic APIs & Gateway SSE Stream (Port 8080)
      // Existing Gateway live event stream - strictly routed to Gateway!
      '/api/v1/traffic/events': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/v1/traffic': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/traffic': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },

      // 3. Controller General APIs & Admin Operations (Port 8000)
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/internal': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },

      // 4. Gateway Client & Application APIs (Port 8080)
      '/api/records': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/data': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/ecommerce': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/shop': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
