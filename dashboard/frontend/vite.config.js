import { defineConfig } from 'vite'

export default defineConfig(({ mode }) => ({
  base: '',
  build: {
    outDir: 'dist'
  },
  server: {
    proxy: mode === 'development'
      ? {
          '/api': {
            target: 'http://localhost:8000', // tu backend FastAPI local
            changeOrigin: true,
            rewrite: (path) => path.replace(/^\/api/, ''),
            // opcional: si querés quitar el prefijo /api al llegar al backend
            // rewrite: (path) => path.replace(/^\/api/, ''),
          },
        }
      : undefined,
  },
}))
