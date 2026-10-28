import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../config'
import CardImage from '../components/CardImage'
import Modal from '../components/Modal'
import CollectionFields from '../components/CollectionFields'
import { EMPTY_ENTRY, entryBody } from '../components/collectionEntry'
import { btn, cardPath, money } from '../components/ui'

// Same list as the watchlist on the Market home, on the light "My cards" side
function Watchlist() {
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [moving, setMoving] = useState(null)       // the card being moved to the collection
  const [entry, setEntry] = useState(EMPTY_ENTRY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function loadCards() {
    apiFetch('/all-cards')
      .then(res => {
        if (res.status === 401) { return null }
        return res.json()
      })
      .then(data => {
        if (data) setCards(data.cards || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadCards() }, [])

  function deleteCard(productId) {
    if (!confirm('Remove this card from your watchlist?')) return
    apiFetch(`/delete-card/${productId}`, { method: 'DELETE' })
      .then(() => loadCards())
  }

  function startMove(card) {
    setMoving(card)
    setEntry(EMPTY_ENTRY)
    setError('')
  }

  // Adds it to the collection and takes it off the watchlist in one request (from_watchlist).
  // The card itself is kept: the collection entry points at it.
  async function move(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await apiFetch(`/add-to-collection/${moving.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: entryBody(entry, { from_watchlist: true }),
      })
      const data = await res.json()
      if (!data.success) throw new Error(data.error || 'Could not move this card.')
      setNotice(`Moved ${moving.name} to your collection.`)
      setMoving(null)
      loadCards()
    } catch (err) {
      setError(err.message || 'Could not move this card.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-4 mb-6">
        <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Watchlist</h1>
        {!loading && cards.length > 0 && (
          <span className="text-sm text-chalk-soft font-medium">{cards.length} {cards.length === 1 ? 'card' : 'cards'}</span>
        )}
      </div>
      <p aria-live="polite" className="text-sm font-semibold text-up-bright -mt-3 mb-4 empty:hidden">{notice}</p>

      {loading ? (
        <div className="h-64 rounded-panel shimmer" aria-hidden="true" />
      ) : cards.length === 0 ? (
        <div className="glass rounded-panel text-center py-16 px-6">
          <p className="font-semibold">No cards on your watchlist yet.</p>
          <p className="text-sm text-chalk-soft mt-1">
            Search for a card on the <Link to="/" className="font-semibold text-chalk underline underline-offset-2">Market</Link> and hit Add.
          </p>
        </div>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-5">
          {cards.map(card => (
            <li key={card.id} className="group relative">
              <Link to={cardPath(card)}
                className="block glass rounded-panel p-3 md:p-4 shadow-float hover:bg-chalk/10 transition-colors">
                <CardImage src={card.image_url} alt={card.name}
                  className="w-full mb-3 transition-transform group-hover:-translate-y-1" />
                <span className="block font-semibold text-[15px] truncate">{card.name}</span>
                <span className="block text-xs text-chalk-soft mb-2 truncate">{card.set_name}</span>
                <span className="block font-display text-lg font-semibold tabular-nums">
                  {card.latest_price ? money(card.latest_price) : <span className="font-sans text-sm font-medium text-chalk-soft">No price</span>}
                </span>
              </Link>
              <button type="button" onClick={() => startMove(card)}
                className="mt-2 w-full rounded-full border border-chalk/15 text-sm font-semibold py-2 hover:bg-chalk/10 transition-colors"
                aria-label={`Move ${card.name} to your collection`}>
                Move to collection
              </button>
              <button
                type="button"
                onClick={() => deleteCard(card.id)}
                aria-label={`Remove ${card.name} from watchlist`}
                title="Remove from watchlist"
                className="absolute top-2 right-2 w-8 h-8 rounded-full bg-chalk/[0.06] text-chalk border border-chalk/10 hover:bg-down-bright hover:text-stage hover:border-down-bright opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 transition flex items-center justify-center shadow-float"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="w-3.5 h-3.5" aria-hidden="true">
                  <path d="M6 6l12 12M18 6 6 18" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}

      {moving && (
        <Modal title="Move to collection" subtitle={`${moving.name}, ${moving.set_name}`} onClose={() => setMoving(null)}>
          <form onSubmit={move} noValidate>
            <CollectionFields entry={entry} setEntry={setEntry} />
            <p className="text-xs text-chalk-soft mt-3">It leaves your watchlist and joins your collection.</p>
            {error && <p role="alert" className="text-sm text-down-bright font-semibold mt-2">{error}</p>}
            <div className="flex gap-3 mt-5">
              <button type="button" onClick={() => setMoving(null)} className={`${btn.secondary} flex-1`}>Cancel</button>
              <button type="submit" disabled={busy} className={`${btn.primary} flex-1`}>{busy ? 'Moving…' : 'Move'}</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}

export default Watchlist
