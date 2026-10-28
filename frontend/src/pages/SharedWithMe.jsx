import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../config'
import { LinkCopy } from '../components/ShareManager'
import { timeLeft } from '../components/share'

// Round initial badge for a username
function Initial({ name, size = 'w-10 h-10 text-base' }) {
  return (
    <span className={`${size} rounded-full bg-chalk text-stage font-display font-semibold flex items-center justify-center shrink-0`} aria-hidden="true">
      {(name || '?').charAt(0).toUpperCase()}
    </span>
  )
}

// One of MY links — expands to show who's opened it
function MyShareRow({ share }) {
  const [open, setOpen] = useState(false)
  const [viewers, setViewers] = useState(null)
  const [loading, setLoading] = useState(false)

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && viewers === null) {
      setLoading(true)
      apiFetch(`/share-viewers/${share.id}`)
        .then(res => res.json())
        .then(d => { setViewers(d); setLoading(false) })
        .catch(() => setLoading(false))
    }
  }

  return (
    <li className="glass rounded-panel overflow-hidden">
      <div className="p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div className="min-w-0">
            <p className="font-semibold truncate">{share.label || 'Untitled link'}</p>
            <p className="text-xs text-chalk-soft">{timeLeft(share.expires_at)}</p>
          </div>
          <button type="button" onClick={toggle} aria-expanded={open}
            className="shrink-0 text-sm font-semibold text-chalk-soft hover:text-chalk flex items-center gap-1 px-2 py-1 rounded-full">
            Who has access
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
              className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </button>
        </div>
        <LinkCopy token={share.token} />
      </div>

      {open && (
        <div className="border-t border-chalk/10 px-4 sm:px-5 py-3">
          {loading ? (
            <p className="text-sm text-chalk-soft">Loading…</p>
          ) : !viewers || viewers.total === 0 ? (
            <p className="text-sm text-chalk-soft">Nobody has opened this link yet.</p>
          ) : (
            <>
              <ul className="space-y-2">
                {viewers.viewers.map((v, i) => (
                  <li key={i} className="flex items-center gap-2.5">
                    <Initial name={v.username} size="w-7 h-7 text-xs" />
                    <span className="text-sm font-semibold truncate">{v.username}</span>
                    <span className="text-xs text-chalk-soft ml-auto shrink-0">
                      {new Date(v.first_opened).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
              {viewers.total > 10 && (
                <p className="text-xs text-chalk-soft mt-3">Showing 10 of {viewers.total} people with access.</p>
              )}
            </>
          )}
        </div>
      )}
    </li>
  )
}

function SharedWithMe() {
  const [shares, setShares] = useState([])
  const [myShares, setMyShares] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      apiFetch('/shared-with-me').then(r => r.json()).catch(() => ({})),
      apiFetch('/my-shares').then(r => r.json()).catch(() => ({})),
    ]).then(([incoming, outgoing]) => {
      setShares(incoming.shares || [])
      setMyShares((outgoing.shares || []).filter(s => s.active))
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="h-64 rounded-panel shimmer" aria-hidden="true" />

  return (
    <>
      <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Shared</h1>
      <p className="text-chalk-soft mt-2 mb-8">Collections shared with you, and links you've sent out.</p>

      {/* Incoming */}
      <h2 className="font-display text-xl font-semibold mb-4">Shared with me</h2>
      {shares.length === 0 ? (
        <div className="glass rounded-panel p-8 text-center mb-12">
          <p className="font-semibold">Nothing shared yet</p>
          <p className="text-sm text-chalk-soft mt-1 max-w-sm mx-auto">
            Ask a friend to share their collection. Once you open their link, it'll show up here.
          </p>
        </div>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
          {shares.map(s => (
            <li key={s.token}>
              <Link to={`/shared/${s.token}`}
                className="block h-full glass rounded-panel p-5 hover:bg-chalk/10 transition-colors">
                <span className="flex items-center gap-3 mb-3">
                  <Initial name={s.owner_name} />
                  <span className="min-w-0">
                    <span className="block font-semibold truncate">{s.owner_name}</span>
                    {s.label && <span className="block text-xs text-chalk-soft truncate">{s.label}</span>}
                  </span>
                </span>
                <span className="block text-sm text-chalk-soft">{timeLeft(s.expires_at)}</span>
                <span className="block text-sm font-semibold mt-3">View their collection and trades →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* Outgoing */}
      <h2 className="font-display text-xl font-semibold mb-4">My shared links</h2>
      {myShares.length === 0 ? (
        <p className="text-sm text-chalk-soft">
          You haven't shared anything yet. Head to your Collection and hit Share to create a link.
        </p>
      ) : (
        <ul className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {myShares.map(s => <MyShareRow key={s.id} share={s} />)}
        </ul>
      )}
    </>
  )
}

export default SharedWithMe
