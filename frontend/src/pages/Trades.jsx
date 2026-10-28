import { useState, useEffect, useId } from 'react'
import { apiFetch } from '../config'
import CardImage from '../components/CardImage'
import Change from '../components/Change'
import { btn, field, label, money, signedMoney, upDown } from '../components/ui'
import useDismiss from '../components/useDismiss'

// Search box that calls onAdd(card) when a result is picked
function CardSearch({ onAdd }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [open, setOpen] = useState(false)
  const boxRef = useDismiss(open, () => setOpen(false))
  const inputId = useId()

  // Short queries clear right away; longer ones search after a pause
  function onQueryChange(value) {
    setQuery(value)
    setOpen(true)
    if (value.length < 2) { setResults([]); setSearching(false) }
    else setSearching(true)
  }

  useEffect(() => {
    if (query.length < 2) return
    const timeout = setTimeout(() => {
      apiFetch(`/poketrace-search/${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => { setResults(data.results || []); setSearching(false) })
        .catch(() => setSearching(false))
    }, 400)
    return () => clearTimeout(timeout)
  }, [query])

  function choose(r) {
    onAdd({
      poketrace_id: r.poketrace_id,
      name: r.name,
      set_name: r.set_name,
      image: r.image,
      display_price: r.display_price,
    })
    setQuery('')
    setResults([])
  }

  return (
    <div ref={boxRef} className="relative">
      <label htmlFor={inputId} className="sr-only">Search a card to add</label>
      <input
        id={inputId}
        type="text"
        value={query}
        onChange={e => onQueryChange(e.target.value)}
        onFocus={() => setOpen(true)}
        placeholder="Search a card to add…"
        autoComplete="off"
        className={`${field} text-sm pr-11`}
      />
      {query && (
        <button type="button" aria-label="Clear search"
          onClick={() => { onQueryChange(''); document.getElementById(inputId)?.focus() }}
          className="absolute right-1.5 top-1 w-8 h-8 rounded-full flex items-center justify-center text-chalk-soft hover:text-chalk hover:bg-chalk/5 transition-colors">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="w-3.5 h-3.5" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      )}
      <p aria-live="polite" className="text-xs text-chalk-soft mt-1 empty:hidden">{searching ? 'Searching…' : ''}</p>
      {open && results.length > 0 && (
        <ul className="absolute z-20 left-0 right-0 mt-1 bg-stage-raised border border-chalk/10 rounded-[20px] max-h-64 overflow-y-auto shadow-float p-1">
          {results.map(r => (
            <li key={r.poketrace_id}>
              <button type="button" onClick={() => choose(r)}
                className="w-full text-left px-2.5 py-2 rounded-[14px] hover:bg-chalk/10 flex items-center gap-2.5">
                <CardImage src={r.image} alt="" className="w-8" />
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-semibold truncate">{r.name}</span>
                  <span className="block text-xs text-chalk-soft truncate">{r.set_name}{r.number && ` #${r.number}`}</span>
                </span>
                {r.display_price && <span className="text-xs text-chalk-soft tabular-nums">${r.display_price}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// One side of the trade — a list of cards, each with an editable agreed value
function BundleSide({ title, cards, setCards }) {
  function addCard(card) {
    setCards([...cards, { ...card, agreed_value: '' }])
  }
  function removeCard(idx) {
    setCards(cards.filter((_, i) => i !== idx))
  }
  function setValue(idx, val) {
    setCards(cards.map((c, i) => i === idx ? { ...c, agreed_value: val } : c))
  }

  const total = cards.reduce((sum, c) => sum + (parseFloat(c.agreed_value) || 0), 0)

  return (
    <fieldset className="rounded-[20px] border border-chalk/10 bg-chalk/[0.06] p-4 min-w-0">
      <legend className="font-semibold px-1">{title}</legend>
      <CardSearch onAdd={addCard} />
      <ul className="mt-3 space-y-2">
        {cards.length === 0 && <li className="text-sm text-chalk-soft">No cards added yet.</li>}
        {cards.map((c, idx) => (
          <li key={idx} className="flex items-center gap-2.5 bg-chalk/[0.06] rounded-[14px] p-2">
            <CardImage src={c.image} alt="" className="w-8" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate">{c.name}</p>
              <p className="text-xs text-chalk-soft truncate">Market {c.display_price ? `$${c.display_price}` : '—'}</p>
            </div>
            <input type="number" placeholder="Value $" value={c.agreed_value}
              aria-label={`Agreed value for ${c.name}`}
              onChange={e => setValue(idx, e.target.value)}
              className={`${field} w-24 text-sm px-2.5 py-1.5`} />
            <button type="button" onClick={() => removeCard(idx)} aria-label={`Remove ${c.name}`}
              className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-chalk-soft hover:text-down-bright hover:bg-down-bright/10 transition-colors">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="w-3.5 h-3.5" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
            </button>
          </li>
        ))}
      </ul>
      {cards.length > 0 && (
        <p className="text-sm text-chalk-soft mt-3 text-right">Agreed total <span className="text-chalk font-bold tabular-nums">{money(total)}</span></p>
      )}
    </fieldset>
  )
}

function TradeSide({ title, total, cards }) {
  return (
    <div>
      <h3 className="text-sm font-semibold mb-2">
        {title} <span className="font-normal text-chalk-soft">market {total != null ? money(total) : '—'}</span>
      </h3>
      <ul>
        {cards.map((c, i) => (
          <li key={i} className="flex flex-wrap justify-between gap-x-3 text-sm py-1.5 border-t border-chalk/10">
            <span className="min-w-0 break-words">{c.name}</span>
            <span className="text-chalk-soft tabular-nums">agreed {money(c.agreed)}, now {money(c.market_now)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Trades() {
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)

  const [gaveCards, setGaveCards] = useState([])
  const [gotCards, setGotCards] = useState([])
  const [cashDirection, setCashDirection] = useState('none')
  const [cashAmount, setCashAmount] = useState('')
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().slice(0, 10))
  const [notes, setNotes] = useState('')

  function loadTrades() {
    apiFetch('/trades')
      .then(res => res.json())
      .then(data => { setTrades(data.trades || []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadTrades() }, [])

  async function ensureCard(card) {
    const res = await apiFetch(`/save-card-poketrace/${encodeURIComponent(card.poketrace_id)}?watchlist=0`)
    const data = await res.json()
    return data.product_id || null
  }

  function resetForm() {
    setGaveCards([]); setGotCards([])
    setCashDirection('none'); setCashAmount('')
    setTradeDate(new Date().toISOString().slice(0, 10)); setNotes('')
  }

  async function submitTrade() {
    if (gaveCards.length === 0 || gotCards.length === 0) {
      alert('Add at least one card on each side.')
      return
    }
    setSaving(true)
    try {
      // Save every card into our system to get product_ids
      const gavePayload = []
      for (const c of gaveCards) {
        const pid = await ensureCard(c)
        gavePayload.push({ product_id: pid, name: c.name, agreed_value: parseFloat(c.agreed_value) || 0 })
      }
      const gotPayload = []
      for (const c of gotCards) {
        const pid = await ensureCard(c)
        gotPayload.push({ product_id: pid, name: c.name, agreed_value: parseFloat(c.agreed_value) || 0 })
      }

      const res = await apiFetch('/log-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trade_date: tradeDate,
          cash_amount: parseFloat(cashAmount) || 0,
          cash_direction: cashDirection,
          notes,
          gave: gavePayload,
          got: gotPayload,
        }),
      })
      const data = await res.json()
      if (data.success) {
        setShowForm(false)
        resetForm()
        loadTrades()
      } else {
        alert(data.error || 'Failed to log trade')
      }
    } catch {
      alert('Something went wrong saving the trade.')
    } finally {
      setSaving(false)
    }
  }

  function deleteTrade(id) {
    if (!confirm('Delete this trade record?')) return
    apiFetch(`/delete-trade/${id}`, { method: 'DELETE' }).then(() => loadTrades())
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Trades</h1>
        <button type="button" onClick={() => { setShowForm(!showForm); if (showForm) resetForm() }}
          aria-expanded={showForm}
          className={showForm ? `${btn.secondary} py-2.5` : `${btn.primary} py-2.5`}>
          {showForm ? 'Cancel' : 'Log a trade'}
        </button>
      </div>

      {showForm && (
        <section aria-labelledby="log-trade-heading" className="glass rounded-panel p-5 sm:p-6 mb-10">
          <h2 id="log-trade-heading" className="font-display text-xl font-semibold mb-4">Log a trade</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <BundleSide title="Cards you gave away" cards={gaveCards} setCards={setGaveCards} />
            <BundleSide title="Cards you received" cards={gotCards} setCards={setGotCards} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label htmlFor="trade-cash" className={label}>Cash involved?</label>
              <div className="flex gap-2">
                <select id="trade-cash" value={cashDirection} onChange={e => setCashDirection(e.target.value)}
                  className={`${field} w-auto`}>
                  <option value="none">No cash</option>
                  <option value="paid">I paid cash</option>
                  <option value="received">I got cash</option>
                </select>
                <input type="number" placeholder="0.00" value={cashAmount} aria-label="Cash amount"
                  disabled={cashDirection === 'none'}
                  onChange={e => setCashAmount(e.target.value)}
                  className={`${field} flex-1 min-w-0 disabled:opacity-40`} />
              </div>
            </div>
            <div>
              <label htmlFor="trade-date" className={label}>Trade date</label>
              <input id="trade-date" type="date" value={tradeDate} onChange={e => setTradeDate(e.target.value)} className={field} />
            </div>
            <div>
              <label htmlFor="trade-notes" className={label}>Notes</label>
              <input id="trade-notes" type="text" placeholder="League night" value={notes}
                onChange={e => setNotes(e.target.value)} className={field} />
            </div>
          </div>
          <button type="button" onClick={submitTrade} disabled={saving} className={`${btn.primary} mt-6 w-full sm:w-auto`}>
            {saving ? 'Saving…' : 'Save trade'}
          </button>
        </section>
      )}

      {loading ? (
        <div className="h-48 rounded-panel shimmer" aria-hidden="true" />
      ) : trades.length === 0 ? (
        <div className="glass rounded-panel text-center py-16 px-6">
          <p className="font-semibold">No trades logged yet.</p>
          <p className="text-sm text-chalk-soft mt-1">Use “Log a trade” to record one.</p>
        </div>
      ) : (
        <ul className="space-y-4">
          {trades.map(t => (
            <li key={t.id} className="glass rounded-panel p-5 sm:p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <p className="text-sm text-chalk-soft">{new Date(t.trade_date).toLocaleDateString()}</p>
                <div className="flex items-start gap-4">
                  <div className="text-right">
                    {t.pct_now == null
                      ? <span className="font-bold text-chalk-soft">—</span>
                      : <Change value={t.pct_now} className="text-lg" />}
                    <span className={`block text-xs tabular-nums ${t.net_now == null ? 'text-chalk-soft' : upDown(t.net_now)}`}>
                      {signedMoney(t.net_now)} now
                    </span>
                  </div>
                  <button type="button" onClick={() => deleteTrade(t.id)} className={btn.danger}>Delete</button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <TradeSide title="Gave" total={t.gave_market_total} cards={t.gave_cards} />
                <TradeSide title="Got" total={t.got_market_total} cards={t.got_cards} />
              </div>
              {t.cash_direction !== 'none' && (
                <p className="text-sm text-chalk-soft mt-4">
                  Cash: {t.cash_direction === 'paid' ? 'you paid' : 'you received'} {money(t.cash_amount)}
                </p>
              )}
              {t.notes && <p className="text-sm text-chalk-soft mt-1 italic break-words">{t.notes}</p>}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export default Trades
