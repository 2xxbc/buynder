import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '../config'
import Modal from './Modal'
import { btn, field, label as labelClass } from './ui'
import { copyText, shareUrl, timeLeft } from './share'

// The share link in a read-only box (so it can be copied by hand) + a Copy button
export function LinkCopy({ token }) {
  const [status, setStatus] = useState('') // '' | 'copied' | 'manual'
  const inputRef = useRef(null)
  const url = shareUrl(token)

  async function copy() {
    const ok = await copyText(url)
    if (!ok) inputRef.current?.select()
    setStatus(ok ? 'copied' : 'manual')
    setTimeout(() => setStatus(''), 2500)
  }

  return (
    <div>
      <div className="flex gap-2">
        <input ref={inputRef} type="text" readOnly value={url} aria-label="Share link"
          onFocus={e => e.target.select()}
          className={`${field} text-xs py-2 min-w-0`} />
        <button type="button" onClick={copy}
          className="shrink-0 rounded-full bg-chalk text-stage text-sm font-semibold px-4 hover:bg-chalk/85 transition-colors">
          {status === 'copied' ? 'Copied' : 'Copy'}
        </button>
      </div>
      <p aria-live="polite" className="text-xs text-chalk-soft mt-1 min-h-4">
        {status === 'manual' && 'Copying isn’t available here. The link is selected, so press Ctrl+C (or ⌘C).'}
      </p>
    </div>
  )
}

function ShareManager() {
  const [open, setOpen] = useState(false)
  const [shares, setShares] = useState([])
  const [duration, setDuration] = useState('24h')
  const [label, setLabel] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (open) loadShares()
  }, [open])

  function loadShares() {
    apiFetch('/my-shares')
      .then(res => res.json())
      .then(data => setShares(data.shares || []))
      .catch(() => {})
  }

  function createShare() {
    setCreating(true)
    apiFetch('/create-share', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration, label }),
    })
      .then(res => res.json())
      .then(data => {
        setCreating(false)
        if (data.success) {
          setLabel('')
          loadShares()
        } else {
          alert(data.error || 'Failed to create link')
        }
      })
      .catch(() => setCreating(false))
  }

  function revokeShare(id) {
    if (!confirm('Turn off this share link? The person will lose access.')) return
    apiFetch(`/revoke-share/${id}`, { method: 'POST' })
      .then(() => loadShares())
  }

  const active = shares.filter(s => s.active)

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={`${btn.secondary} py-2.5`}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4" aria-hidden="true">
          <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7" /><path d="M16 6l-4-4-4 4" /><path d="M12 2v13" />
        </svg>
        Share
      </button>

      {open && (
        <Modal wide title="Share your collection and trades" onClose={() => setOpen(false)}
          subtitle="Create a view-only link. Anyone logged in who opens it can see your collection and trades until it expires.">
          {/* Create a new link */}
          <div className="glass rounded-[20px] p-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label htmlFor="share-duration" className={labelClass}>Viewable for</label>
                <select id="share-duration" value={duration} onChange={e => setDuration(e.target.value)} className={field}>
                  <option value="1h">1 hour</option>
                  <option value="12h">12 hours</option>
                  <option value="24h">24 hours</option>
                  <option value="infinite">No expiry (until I turn it off)</option>
                </select>
              </div>
              <div>
                <label htmlFor="share-label" className={labelClass}>Label (optional)</label>
                <input id="share-label" type="text" value={label} onChange={e => setLabel(e.target.value)}
                  placeholder="For Jake" className={field} />
              </div>
            </div>
            <button type="button" onClick={createShare} disabled={creating} className={`${btn.primary} w-full`}>
              {creating ? 'Creating…' : 'Create link'}
            </button>
          </div>

          {/* Existing links */}
          <h3 className="font-semibold mt-6 mb-2">Your active links</h3>
          {active.length === 0 ? (
            <p className="text-sm text-chalk-soft">No active links yet.</p>
          ) : (
            <ul className="space-y-3">
              {active.map(s => (
                <li key={s.id} className="rounded-[20px] border border-chalk/10 p-4">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <span className="text-sm font-semibold truncate">{s.label || 'Untitled link'}</span>
                    <span className="text-xs text-chalk-soft shrink-0">{timeLeft(s.expires_at)}</span>
                  </div>
                  <LinkCopy token={s.token} />
                  <button type="button" onClick={() => revokeShare(s.id)} className={`${btn.danger} mt-1`}>
                    Turn off
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
    </>
  )
}

export default ShareManager
