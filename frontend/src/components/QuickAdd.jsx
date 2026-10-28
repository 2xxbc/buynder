import { useEffect, useId, useRef, useState } from 'react'
import { apiFetch } from '../config'
import Modal from './Modal'
import useCardSearch from './useCardSearch'
import CardImage from './CardImage'
import CollectionFields from './CollectionFields'
import { EMPTY_ENTRY, entryBody } from './collectionEntry'
import { btn, conditionLabel, field, money } from './ui'

// "Add cards" on the Collection page: search → pick a card → condition, quantity, price paid → Add.
// It stays open so you can add several in a row; what you added is listed at the bottom.
// Saving uses the same two steps as everywhere else: /save-card-poketrace (watchlist=0, so it doesn't
// land on the watchlist), then /add-to-collection with the product id that step returns.
export default function QuickAdd({ onClose, onAdded }) {
  const searchId = useId()
  const searchRef = useRef(null)
  const conditionRef = useRef(null)
  const [query, setQuery] = useState('')
  const search = useCardSearch(query)
  const results = search.results
  const searching = search.searching
  const [picked, setPicked] = useState(null)
  const [entry, setEntry] = useState(EMPTY_ENTRY)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  const [added, setAdded] = useState([])

  function onQueryChange(value) {
    setQuery(value)
  }

  // Picking a card moves focus to its first field; going back returns it to the search box
  useEffect(() => {
    if (picked) conditionRef.current?.focus()
    else searchRef.current?.focus()
  }, [picked])

  function pick(card) {
    setPicked(card)
    setEntry(e => ({ ...EMPTY_ENTRY, condition: e.condition }))  // keep the last condition: batches are often alike
    setError('')
  }

  async function add(e) {
    e.preventDefault()
    if (!picked || adding) return
    setAdding(true)
    setError('')
    try {
      const saveRes = await apiFetch(`/save-card-poketrace/${encodeURIComponent(picked.poketrace_id)}?watchlist=0`)
      const saved = await saveRes.json()
      if (!saved.product_id) throw new Error(saved.error || 'Could not save this card.')
      const res = await apiFetch(`/add-to-collection/${saved.product_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: entryBody(entry),
      })
      const data = await res.json()
      if (!data.success) throw new Error(data.error || 'Could not add this card.')
      setAdded(list => [{ ...picked, ...entry, key: `${picked.poketrace_id}-${Date.now()}` }, ...list])
      setPicked(null)
      onAdded?.()
    } catch (err) {
      setError(err.message || 'Could not add this card.')
    } finally {
      setAdding(false)
    }
  }

  return (
    <Modal wide title="Add cards" subtitle="Search, pick, add. It stays open for the next one." onClose={onClose}>
      {!picked ? (
        <>
          <label htmlFor={searchId} className="sr-only">Search any Pokémon card</label>
          <input id={searchId} ref={searchRef} type="search" value={query} autoComplete="off"
            onChange={e => onQueryChange(e.target.value)} placeholder="Search a card, e.g. Charizard"
            className={field} />
          <p aria-live="polite" className="text-xs text-chalk-soft mt-2 min-h-4">
            {searching ? 'Searching…' : query.trim().length >= 2 && results.length === 0 ? (search.hint || 'No cards found. Try the name plus a set word ("absol magma") or a card number.') : ''}
          </p>
          {results.length > 0 && (
            <ul className="mt-1 -mx-2 max-h-[45vh] overflow-y-auto">
              {results.map(r => (
                <li key={r.poketrace_id}>
                  <button type="button" onClick={() => pick(r)}
                    className="w-full text-left px-2 py-2 rounded-[14px] hover:bg-chalk/10 flex items-center gap-3">
                    <CardImage src={r.image} alt="" className="w-10" />
                    <span className="flex-1 min-w-0">
                      <span className="block font-semibold truncate">{r.name}</span>
                      <span className="block text-sm text-chalk-soft truncate">{r.set_name}{r.number && ` #${r.number}`}</span>
                    </span>
                    {r.display_price != null && <span className="text-sm text-chalk-soft tabular-nums">{money(r.display_price)}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {search.hasMore && (
            <button type="button" onClick={search.loadMore} disabled={search.loadingMore}
              className="mt-2 w-full rounded-full border border-chalk/15 text-sm font-semibold py-2.5 hover:bg-chalk/10 disabled:opacity-60 transition-colors">
              {search.loadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </>
      ) : (
        <form onSubmit={add} noValidate>
          <div className="flex items-center gap-3 mb-4">
            <CardImage src={picked.image} alt={picked.name} className="w-14" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold truncate">{picked.name}</p>
              <p className="text-sm text-chalk-soft truncate">{picked.set_name}{picked.number && ` #${picked.number}`}</p>
            </div>
          </div>
          <CollectionFields entry={entry} setEntry={setEntry} firstFieldRef={conditionRef} />
          {error && <p role="alert" className="text-sm text-down-bright font-semibold mt-3">{error}</p>}
          <div className="flex gap-3 mt-5">
            <button type="button" onClick={() => setPicked(null)} className={`${btn.secondary} flex-1`}>Back</button>
            <button type="submit" disabled={adding} className={`${btn.primary} flex-1`}>{adding ? 'Adding…' : 'Add'}</button>
          </div>
        </form>
      )}

      {added.length > 0 && (
        <section aria-labelledby={`${searchId}-added`} className="mt-6 pt-4 border-t border-chalk/10">
          <h3 id={`${searchId}-added`} className="text-sm font-semibold">Just added ({added.length})</h3>
          <ul className="mt-2 space-y-1.5" aria-live="polite">
            {added.map(a => (
              <li key={a.key} className="flex items-start gap-2 text-sm">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" className="w-4 h-4 mt-0.5 text-up-bright shrink-0" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>
                <span className="min-w-0 break-words"><span className="font-semibold">{a.name}</span> · {conditionLabel(a.condition)} · qty {a.quantity}{a.price_paid.trim() !== '' && ` · paid ${money(a.price_paid)}`}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Modal>
  )
}
