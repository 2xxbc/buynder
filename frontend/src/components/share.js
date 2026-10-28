// Helpers for share links (used by ShareManager and the Shared page)

// Copy text; returns false when the clipboard isn't available (plain http, e.g. a LAN address)
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export const shareUrl = token => `${window.location.origin}/shared/${token}`

export function timeLeft(expiresAt) {
  if (!expiresAt) return 'No expiry'
  const ms = new Date(expiresAt).getTime() - Date.now()
  if (ms <= 0) return 'Expired'
  const hrs = Math.floor(ms / 3600000)
  const mins = Math.floor((ms % 3600000) / 60000)
  return `${hrs}h ${mins}m left`
}
