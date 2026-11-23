import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const sharePort = Number(process.env.VITE_SHARE_PORT || 3840)

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: 'dist-share',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        share: fileURLToPath(new URL('./share.html', import.meta.url)),
        evalShare: fileURLToPath(new URL('./evalShare.html', import.meta.url)),
        labShare: fileURLToPath(new URL('./labShare.html', import.meta.url)),
      },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: sharePort,
    open: '/share.html',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/autobi': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass(req) {
          if (req.headers?.accept?.includes('text/html')) {
            return '/share.html'
          }
        },
        rewrite: (p) => p.replace(/^\/autobi/, '/api/autobi'),
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: sharePort,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/autobi': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/autobi/, '/api/autobi'),
      },
    },
  },
})
