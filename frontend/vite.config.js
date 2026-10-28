import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  // LAN / Tailscale addresses the site may be opened at: DEV_HOSTS from the repo's .env (comma-separated),
  // the same list app.py uses. The 'DEV_HOSTS' prefix means only that one line is read, and it never
  // reaches the browser (only VITE_* variables do).
  const env = loadEnv(mode, path.resolve(import.meta.dirname, '..'), 'DEV_HOSTS')
  const devHosts = (env.DEV_HOSTS || '').split(',').map((h) => h.trim()).filter(Boolean)

  return {
    plugins: [react(), tailwindcss()],
    // Dev server (npm run dev) — separate port so it never fights the live service
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      allowedHosts: ['localhost', ...devHosts],
    },
    // Preview server (the old systemd service, before Caddy) — serves the production build
    preview: {
      host: '0.0.0.0',
      port: 5180,
      strictPort: true,
      allowedHosts: ['buyndermarket.com', 'www.buyndermarket.com', 'localhost', ...devHosts],
    },
  }
})
