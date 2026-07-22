import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Dev server (npm run dev) — separate port so it never fights the live service
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: ['localhost', '10.0.0.84', '100.107.77.5'],
  },
  // Preview server (the systemd service) — serves the production build
  preview: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    allowedHosts: ['buyndermarket.com', 'www.buyndermarket.com', 'localhost', '10.0.0.84', '100.107.77.5'],
  },
})
