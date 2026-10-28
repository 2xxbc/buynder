import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../config'
import { useAuth } from '../AuthContext'
import CardImage from '../components/CardImage'
import { btn, money } from '../components/ui'

function SharedView() {
  const { token } = useParams()
  const { user, loading: authLoading } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (authLoading || !user) return
    apiFetch(`/shared/${token}`)
      .then(res => res.json().then(d => ({ ok: res.ok, d })))
      .then(({ ok, d }) => {
        if (ok) setData(d)
        else setError(d.error || 'Could not load this link.')
        setLoading(false)
      })
      .catch(() => { setError('Something went wrong.'); setLoading(false) })
  }, [token, user, authLoading])

  // Live countdown: tick once a second while the link has an expiry
  useEffect(() => {
    if (!data?.expires_at) return
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [data])

  let timeLeft = ''
  let expired = false
  if (data) {
    if (!data.expires_at) timeLeft = 'No expiry'
    else {
      const ms = new Date(data.expires_at).getTime() - now
      if (ms <= 0) { timeLeft = 'Expired'; expired = true }
      else {
        const hrs = Math.floor(ms / 3600000)
        const mins = Math.floor((ms % 3600000) / 60000)
        const secs = Math.floor((ms % 60000) / 1000)
        timeLeft = `${hrs}h ${mins}m ${secs}s left`
      }
    }
  }
  const shownError = error || (expired ? 'This share link has expired.' : '')

  if (authLoading || (user && loading)) {
    return <div className="h-64 rounded-panel shimmer" aria-hidden="true" />
  }

  // Must be logged in to view a shared link
  if (!user) {
    return (
      <div className="max-w-md mx-auto text-center glass rounded-panel p-8 sm:p-10 my-10">
        <h1 className="font-display text-2xl font-semibold">Log in to view this</h1>
        <p className="text-chalk-soft mt-3">Someone shared their collection with you. Log in or create an account to see it.</p>
        <div className="flex flex-wrap gap-3 justify-center mt-6">
          <Link to="/login" className={btn.secondary}>Log in</Link>
          <Link to="/signup" className={btn.primary}>Create account</Link>
        </div>
      </div>
    )
  }

  if (shownError) {
    return (
      <div className="max-w-md mx-auto text-center glass rounded-panel p-8 sm:p-10 my-10">
        <h1 className="font-display text-2xl font-semibold">{shownError}</h1>
        <Link to="/" className={`${btn.primary} mt-6`}>Back to Market</Link>
      </div>
    )
  }

  if (!data) return null

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div className="min-w-0">
          <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight break-words">{data.owner_name}'s collection</h1>
          <p className="text-chalk-soft mt-1">View-only shared link</p>
        </div>
        <p className="glass rounded-full px-4 py-2 text-sm">
          <span className="text-chalk-soft">Access: </span>
          <span className="font-semibold tabular-nums">{timeLeft}</span>
        </p>
      </div>

      {/* Collection */}
      <h2 className="font-display text-xl font-semibold mb-4">Collection <span className="text-chalk-soft">({data.collection.length})</span></h2>
      {data.collection.length === 0 ? (
        <p className="text-chalk-soft mb-10">No cards in their collection.</p>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4 mb-12">
          {data.collection.map((c, i) => (
            <li key={i} className="glass rounded-[20px] p-3 sm:p-4">
              <CardImage src={c.image_url} alt={c.name} className="w-full mb-3" />
              <p className="font-semibold text-sm sm:text-base truncate">{c.name}</p>
              <p className="text-xs sm:text-sm text-chalk-soft truncate">{c.set_name}</p>
              <p className="font-display text-lg font-semibold tabular-nums mt-2">{money(c.current_price)}</p>
              <p className="text-xs text-chalk-soft mt-0.5">Qty {c.quantity}{c.price_paid != null && <>, paid {money(c.price_paid)}</>}</p>
            </li>
          ))}
        </ul>
      )}

      {/* Trades */}
      <h2 className="font-display text-xl font-semibold mb-4">Trades <span className="text-chalk-soft">({data.trades.length})</span></h2>
      {data.trades.length === 0 ? (
        <p className="text-chalk-soft">No trades logged.</p>
      ) : (
        <ul className="space-y-3">
          {data.trades.map(t => (
            <li key={t.id} className="glass rounded-panel p-4 sm:p-5">
              <p className="text-sm text-chalk-soft mb-3">{new Date(t.trade_date).toLocaleDateString()}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <h3 className="text-sm font-semibold mb-1">Gave</h3>
                  {t.gave_cards.map((c, i) => (
                    <p key={i} className="text-sm">{c.name} <span className="text-chalk-soft tabular-nums">({money(c.agreed)})</span></p>
                  ))}
                </div>
                <div>
                  <h3 className="text-sm font-semibold mb-1">Got</h3>
                  {t.got_cards.map((c, i) => (
                    <p key={i} className="text-sm">{c.name} <span className="text-chalk-soft tabular-nums">({money(c.agreed)})</span></p>
                  ))}
                </div>
              </div>
              {t.cash_direction !== 'none' && (
                <p className="text-sm text-chalk-soft mt-3">Cash {t.cash_direction === 'paid' ? 'paid' : 'received'}: {money(t.cash_amount)}</p>
              )}
              {t.notes && <p className="text-sm text-chalk-soft mt-1 italic break-words">{t.notes}</p>}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export default SharedView
