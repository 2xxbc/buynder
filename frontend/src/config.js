// Public domain: the API is on the SAME address, under /api (Caddy passes it to Flask). The login
// cookie then belongs to buyndermarket.com itself, so Safari's cross-site tracking protection has
// nothing to block (a cookie from the separate api.buyndermarket.com address is at its mercy).
// Local/LAN/Tailscale hit the API port directly: the dev server (npm run dev) talks to the
// dev API on 5051 (scripts/dev-api.sh), the prod build talks to the live API on 5050.
const host = window.location.hostname
const apiPort = import.meta.env.DEV ? 5051 : 5050

export const API_URL = host.endsWith('buyndermarket.com')
  ? `${window.location.origin}/api`
  : `http://${host}:${apiPort}`

// Wrapper around fetch that always sends the session cookie.
export function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
  })
}
