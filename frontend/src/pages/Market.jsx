import { useState, useEffect } from 'react'
import { TRENDING } from '../names'
import { Link } from 'react-router-dom'
import { apiFetch } from '../config'
import { useAuth } from '../AuthContext'
import CardImage from '../components/CardImage'
import Change from '../components/Change'
import { cardPath, money } from '../components/ui'
import useDismiss from '../components/useDismiss'
import useCardSearch from '../components/useCardSearch'

// Showroom hero: the week's top gainer on a foil tile, with a paper price ticket
function FeaturedCard({ card }) {
  // Still loading: same footprint as the real tile so nothing jumps when it arrives
  if (!card) {
    return (
      <div className="mx-auto w-full max-w-[19rem] sm:max-w-[26rem] pb-14" aria-hidden="true">
        <div className="aspect-[4/5] clip-corner shimmer" />
      </div>
    )
  }

  return (
    <div className="relative mx-auto w-full max-w-[19rem] sm:max-w-[26rem] pb-14">
      <div className="aspect-[4/5] clip-corner bg-foil flex items-center justify-center">
        <CardImage src={card.image_url} alt={card.name} tone="dark"
          className="w-[58%] self-center shadow-glow -rotate-3" />
      </div>

      {/* Paper price ticket — the whole ticket opens the card */}
      <Link to={cardPath(card)}
        className="absolute bottom-0 right-3 sm:-right-4 w-[min(17rem,85%)] text-left bg-ticket text-stage px-5 pt-4 pb-5 rounded-[3px] shadow-float rotate-2 hover:rotate-0 transition-transform focus-visible:outline-volt">
        <span className="absolute top-3 right-3 w-2.5 h-2.5 rounded-full bg-stage" aria-hidden="true" />
        <span className="block text-xs font-semibold text-stage/70">Top gainer this week</span>
        <span className="block font-display text-lg font-semibold leading-tight mt-1 truncate">{card.name}</span>
        <span className="block text-xs text-stage/70 truncate">{card.set_name}</span>
        <span className="flex items-baseline justify-between gap-3 mt-3 pt-3 border-t border-dashed border-stage/25">
          <span className="font-display text-2xl font-semibold tabular-nums">{money(card.price)}</span>
          <Change value={card.pct_7d} tone="light" className="text-sm" />
        </span>
      </Link>
    </div>
  )
}

function MoverTile({ card }) {
  return (
    <Link to={cardPath(card)}
      className="group block w-full text-left p-3 rounded-[4px] bg-stage-raised border border-stage-line hover:border-chalk/30 transition-colors">
      <CardImage src={card.image_url} alt={card.name} tone="dark"
        className="w-full transition-transform group-hover:-translate-y-1" />
      <span className="block mt-3 text-sm font-semibold text-chalk truncate">{card.name}</span>
      <span className="block text-xs text-chalk-soft truncate">{card.set_name}</span>
      <span className="flex items-baseline justify-between gap-2 mt-2 text-sm">
        <span className="tabular-nums text-chalk">{money(card.price)}</span>
        <Change value={card.pct_7d} />
      </span>
    </Link>
  )
}

function NewSetTile({ card }) {
  return (
    <Link to={`/card/${card.poketrace_id}`}
      className="group block w-full text-left p-3 rounded-[4px] bg-stage-raised border border-stage-line hover:border-chalk/30 transition-colors">
      <CardImage src={card.image_url} alt={card.name} className="w-full transition-transform group-hover:-translate-y-1" />
      <span className="block mt-3 text-sm font-semibold text-chalk truncate">{card.name}</span>
      <span className="block text-xs text-chalk-soft truncate">{card.card_number}{card.rarity && ` · ${card.rarity}`}</span>
      <span className="block mt-2 text-sm tabular-nums text-chalk">{money(card.price)}</span>
    </Link>
  )
}

function Market() {
  const { user } = useAuth()
  const [cards, setCards] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [resultsOpen, setResultsOpen] = useState(false)
  const searchRef = useDismiss(resultsOpen, () => setResultsOpen(false))
  const [movers, setMovers] = useState(null) // null = loading, {} = failed
  const [newSet, setNewSet] = useState(null)  // { set, cards } from /new-set; hidden until it has a set

  // Public market data for the hero + trending row (same endpoint as the Trending page)
  useEffect(() => {
    apiFetch('/discovery?window=7d')
      .then(res => res.json())
      .then(d => setMovers(d.error ? {} : d))
      .catch(() => setMovers({}))
  }, [])

  // The home page's set: our featured pick (FEATURED_SET in app.py), or the newest dated English set
  useEffect(() => {
    apiFetch('/new-set')
      .then(res => res.json())
      .then(d => { if (d?.set && d.cards?.length) setNewSet(d) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (user) loadCards()
  }, [user])

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

  // Name + set words, card numbers, optional "ex", and "Load more" (see useCardSearch)
  const search = useCardSearch(query)
  const searchResults = search.results
  const searching = search.searching

  function onQueryChange(value) {
    setQuery(value)
    setResultsOpen(true)
  }

  function saveCard(poketraceId) {
    apiFetch(`/save-card-poketrace/${encodeURIComponent(poketraceId)}`)
      .then(res => res.json())
      .then(() => {
        setQuery('')
        loadCards()
      })
  }

  function deleteCard(productId) {
    if (!confirm('Remove this card from your watchlist?')) return
    apiFetch(`/delete-card/${productId}`, { method: 'DELETE' })
      .then(() => loadCards())
  }

  const featured = movers?.gainers?.[0]
  // Row: the next biggest gainers and losers, biggest moves first
  const moverRow = movers?.gainers
    ? [...movers.gainers.slice(1, 6), ...(movers.losers || []).slice(0, 5)]
        .sort((a, b) => Math.abs(b.pct_7d ?? 0) - Math.abs(a.pct_7d ?? 0))
    : []
  const showTile = movers === null || featured

  return (
    <>
      {/* ── Showroom hero ── */}
      <section className={`grid gap-10 items-center mb-14 md:mb-20 ${showTile ? 'md:grid-cols-[1.15fr_1fr] md:gap-14' : ''}`}>
        <div className="relative z-20">
          <h1 className="font-display font-semibold text-chalk text-[2.1rem] sm:text-5xl lg:text-[3.6rem] leading-[1.05] tracking-tight">
            What's your card worth today?
          </h1>
          <p className="mt-5 text-chalk-soft text-base md:text-lg max-w-lg">
            {movers?.cards_tracked
              ? `Prices for ${movers.cards_tracked.toLocaleString()} Pokémon cards, updated every night.`
              : 'Pokémon card prices, updated every night.'}
          </p>

          <div ref={searchRef} className="relative mt-8 max-w-xl">
            <label htmlFor="card-search" className="sr-only">Search any Pokémon card</label>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-chalk-soft pointer-events-none" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input
              id="card-search"
              type="text"
              value={query}
              onChange={e => onQueryChange(e.target.value)}
              onFocus={() => setResultsOpen(true)}
              placeholder="Search any Pokémon card…"
              autoComplete="off"
              className="w-full bg-stage-raised border border-stage-line rounded-[4px] pl-12 pr-14 py-4 text-chalk placeholder:text-chalk-soft focus:border-volt transition-colors"
            />
            {query && (
              <button type="button" aria-label="Clear search"
                onClick={() => { onQueryChange(''); document.getElementById('card-search')?.focus() }}
                className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full flex items-center justify-center text-chalk-soft hover:text-chalk hover:bg-chalk/10 transition-colors">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="w-4 h-4" aria-hidden="true">
                  <path d="M6 6l12 12M18 6 6 18" />
                </svg>
              </button>
            )}

            {resultsOpen && query.length >= 2 && (
              <div className="absolute z-30 top-full left-0 right-0 mt-2 bg-stage-raised border border-stage-line rounded-[4px] max-h-[26rem] overflow-y-auto shadow-float">
                <p aria-live="polite" className={searching || searchResults.length === 0 ? 'p-4 text-sm text-chalk-soft' : 'sr-only'}>
                  {searching ? 'Searching…' : searchResults.length === 0 ? (search.hint || 'No results found. Try the name plus a set word, like "absol magma", or a card number.') : `${searchResults.length} results`}
                </p>
                <ul>
                  {searchResults.map(card => (
                    <li key={card.poketrace_id} className="flex items-center gap-2 pr-3 border-b border-stage-line last:border-b-0 hover:bg-chalk/5 transition-colors">
                      <Link to={`/card/${card.poketrace_id}`}
                        className="flex-1 min-w-0 flex items-center gap-3 p-3 text-left">
                        <CardImage src={card.image} alt="" tone="dark" className="w-10" />
                        <span className="min-w-0">
                          <span className="block font-semibold text-chalk truncate">{card.name}</span>
                          <span className="block text-sm text-chalk-soft truncate">
                            {card.set_name}
                            {card.number && ` #${card.number}`}
                          </span>
                          {card.rarity && <span className="block text-xs text-chalk-soft truncate">{card.rarity}</span>}
                        </span>
                      </Link>
                      <div className="text-right shrink-0">
                        {card.display_price && (
                          <p className="text-chalk font-bold text-sm tabular-nums">${card.display_price}</p>
                        )}
                        <button
                          type="button"
                          onClick={() => user ? saveCard(card.poketrace_id) : alert('Log in or create an account to save cards.')}
                          aria-label={`Add ${card.name} to watchlist`}
                          className="text-sm bg-volt hover:bg-volt-deep text-stage font-bold px-3 py-1 rounded-[3px] mt-1 transition-colors">Add</button>
                      </div>
                    </li>
                  ))}
                </ul>
                {search.hasMore && (
                  <button type="button" onClick={search.loadMore} disabled={search.loadingMore}
                    className="w-full py-3 text-sm font-semibold text-chalk border-t border-stage-line hover:bg-chalk/5 disabled:opacity-60 transition-colors">
                    {search.loadingMore ? 'Loading…' : 'Load more'}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {showTile && <FeaturedCard card={featured} />}
      </section>

      {/* ── Trending row ── */}
      {moverRow.length > 0 && (
        <section aria-labelledby="movers-heading" className="mb-14 md:mb-20">
          <div className="flex items-baseline justify-between gap-4 mb-5">
            <h2 id="movers-heading" className="font-display text-xl md:text-2xl font-semibold text-chalk">{TRENDING} this week</h2>
            <Link to="/discovery" className="text-sm font-semibold text-chalk-soft hover:text-chalk transition-colors">
              See all {TRENDING} →
            </Link>
          </div>
          <ul className="flex gap-3 md:gap-4 overflow-x-auto snap-x snap-mandatory -mx-4 px-4 md:mx-0 md:px-0 pt-1 pb-3">
            {moverRow.map(card => (
              <li key={card.poketrace_id} className="snap-start shrink-0 w-36 md:w-44">
                <MoverTile card={card} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Featured set (our pick) or New set (newest by release date): its cards, highest price first ── */}
      {newSet && (
        <section aria-labelledby="newset-heading" className="mb-14 md:mb-20">
          <div className="mb-5">
            <h2 id="newset-heading" className="font-display text-xl md:text-2xl font-semibold text-chalk">
              {newSet.set.featured ? 'Featured set' : 'New set'}: {newSet.set.name}
            </h2>
            <p className="text-sm text-chalk-soft mt-1">
              {newSet.set.release_date
                ? `Released ${new Date(newSet.set.release_date).toLocaleDateString(undefined, { timeZone: 'UTC', month: 'long', day: 'numeric', year: 'numeric' })} · highest price first`
                : 'Highest price first'}
            </p>
          </div>
          <ul className="flex gap-3 md:gap-4 overflow-x-auto snap-x snap-mandatory -mx-4 px-4 md:mx-0 md:px-0 pt-1 pb-3">
            {newSet.cards.map(card => (
              <li key={card.poketrace_id} className="snap-start shrink-0 w-36 md:w-44">
                <NewSetTile card={card} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {!user && (
        <p className="text-chalk-soft text-center max-w-md mx-auto py-10">
          <Link to="/signup" className="text-chalk font-semibold underline underline-offset-4 decoration-volt hover:decoration-2">Create an account</Link> to
          save cards, track your collection, and log trades.
        </p>
      )}

      {/* ── Watchlist ── */}
      {user && (
        <div className="flex items-baseline justify-between mb-6">
          <h2 className="font-display text-xl md:text-2xl font-semibold text-chalk">Your watchlist</h2>
          {!loading && cards.length > 0 && (
            <span className="text-sm text-chalk-soft font-medium">{cards.length} {cards.length === 1 ? 'card' : 'cards'}</span>
          )}
        </div>
      )}
      {user && (loading ? (
        <p className="text-chalk-soft text-center py-8">Loading…</p>
      ) : (
        <>
          <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-5">
            {(cards || []).map(card => (
              <li key={card.id} className="group relative">
                <Link to={cardPath(card)}
                  className="block w-full text-left p-3 md:p-3.5 rounded-[4px] bg-stage-raised border border-stage-line hover:border-chalk/30 transition-colors">
                  <CardImage src={card.image_url} alt={card.name} tone="dark"
                    className="w-full mb-3 transition-transform group-hover:-translate-y-1" />
                  <span className="block font-semibold text-[15px] text-chalk truncate">{card.name}</span>
                  <span className="block text-xs text-chalk-soft mb-2 truncate">{card.set_name}</span>
                  <span className="block font-display text-lg font-semibold tabular-nums text-chalk">
                    {card.latest_price ? money(card.latest_price) : <span className="font-sans text-sm font-medium text-chalk-soft">No price</span>}
                  </span>
                </Link>
                <button
                  type="button"
                  onClick={() => deleteCard(card.id)}
                  aria-label={`Remove ${card.name} from watchlist`}
                  title="Remove from watchlist"
                  className="absolute top-2 right-2 w-8 h-8 rounded-full bg-stage/85 text-chalk border border-stage-line hover:bg-down-bright hover:text-stage hover:border-down-bright opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 transition flex items-center justify-center shadow-float"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="w-3.5 h-3.5" aria-hidden="true">
                    <path d="M6 6l12 12M18 6 6 18" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
          {cards.length === 0 && (
            <div className="text-center py-16 border border-dashed border-stage-line rounded-[4px]">
              <p className="text-chalk font-semibold mb-2">No cards saved yet.</p>
              <p className="text-chalk-soft text-sm">Search for a card above and hit Add to start your watchlist.</p>
            </div>
          )}
        </>
      ))}
    </>
  )
}

export default Market
