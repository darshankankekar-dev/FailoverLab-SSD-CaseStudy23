import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/traffic': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/v1/traffic': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
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
