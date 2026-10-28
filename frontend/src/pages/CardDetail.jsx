import { useState, useEffect, useRef } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Line } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip } from 'chart.js'
import { apiFetch } from '../config'
import { useAuth } from '../AuthContext'
import CardImage from '../components/CardImage'
import Change from '../components/Change'
import Modal from '../components/Modal'
import { btn, chip, field, label, money, token, CONDITIONS, conditionLabel } from '../components/ui'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip)

const RANGES = [
  { key: '7d', label: '7d', days: 7, phrase: 'in the last 7 days' },
  { key: '1m', label: '1m', days: 30, phrase: 'in the last month' },
  { key: '3m', label: '3m', days: 90, phrase: 'in the last 3 months' },
  { key: '6m', label: '6m', days: 180, phrase: 'in the last 6 months' },
  { key: '1y', label: '1y', days: 365, phrase: 'in the last year' },
  { key: 'all', label: 'All', days: Infinity, phrase: 'all time' },
]
const PUBLIC_RANGES = ['7d', '1m']

// Only well-formed ids ever reach the API (PokeTrace ids are UUIDs; watchlist ids are numbers)
const isPoketraceId = id => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id || '')
const isProductId = id => /^\d{1,10}$/.test(id || '')

// The backend has no /alerts, /create-alert or /delete-alert routes yet. Flip this on once it does.
const ALERTS_ENABLED = false

// % change over the last N days, using the closest recorded price on or before that day
function changeOver(sorted, latest, days, now) {
  const target = now - days * 86400000
  let past = null
  for (const h of sorted) {
    if (new Date(h.recorded_at).getTime() <= target) past = h.price
  }
  if (!past) return null
  return ((latest - past) / past) * 100
}

const SOURCE_NAMES = { tcgplayer: 'TCGplayer', ebay: 'eBay' }
const sourceName = src => SOURCE_NAMES[src] || src
// PokeTrace dates are calendar days ("2026-10-15"); format them in UTC so they don't shift a day
const dayLabel = (iso, opts = { month: 'short', day: 'numeric', year: 'numeric' }) =>
  new Date(iso).toLocaleDateString(undefined, { timeZone: 'UTC', ...opts })
const saleAmount = s => s.low === s.high ? money(s.low) : `${money(s.low)}–${money(s.high)}`

// "Last sold Oct 15 on TCGplayer for $179.99", or how far back we looked when there's no sale at all
function lastSoldText(info, short = false) {
  const s = info.last_sale
  if (s) return short ? `Last sold ${dayLabel(s.date, { month: 'short', day: 'numeric' })}`
    : `Last sold ${dayLabel(s.date)} on ${s.source} for ${saleAmount(s)}${s.count > 1 ? ` (${s.count} sales that day)` : ''}.`
  if (info.history_from) return short ? 'No sales lately' : `No sales recorded since at least ${dayLabel(info.history_from)}.`
  return ''
}

// Under the big price: which site the number comes from, how many sales back it, and the last real sale
function PriceBasis({ info, countsAvailable }) {
  const n = info.sales_30d
  const others = Object.entries(info.sales_30d_by_source || {}).filter(([src]) => src !== info.source)
  const also = others.length ? ` (plus ${others.map(([src, k]) => `${k} on ${src}`).join(', ')})` : ''
  let text
  if (info.status === 'ok') text = `${info.source === 'eBay' ? 'Recent sales' : `${info.source} market price`} · ${n} sales in the last 30 days${also}`
  else if (info.status === 'low') text = `${info.source === 'eBay' ? 'Based' : `${info.source} price · based`} on only ${n} ${n === 1 ? 'sale' : 'sales'} in the last 30 days${also}`
  else if (info.status === 'none') text = countsAvailable === false
    ? 'TCGplayer hasn\'t updated this price in over 30 days, so we don\'t show it.'
    : 'No sales in the last 30 days on any site we track, so we don\'t show a price for this condition.'
  else text = `${info.source} market price · sale count unavailable right now`
  const last = info.status !== null ? lastSoldText(info) : ''
  return (
    <div className={`mt-2 text-sm ${info.status === 'low' || info.status === 'none' ? 'text-chalk' : 'text-chalk-soft'}`}>
      <p className={info.status === 'low' || info.status === 'none' ? 'font-medium' : ''}>
        {info.status === 'low' && <span className="inline-block mr-2 px-2 py-0.5 rounded-full bg-chalk/[0.07] text-xs font-semibold">Low data</span>}
        {info.source === 'eBay' && <span className="inline-block mr-2 px-2 py-0.5 rounded-full bg-chalk text-stage text-xs font-semibold">eBay price</span>}
        {text}
      </p>
      {last && <p className="mt-0.5 text-chalk-soft">{last}</p>}
    </div>
  )
}

// Small lines on each condition button: sales behind the price, which site, and when it last sold
function SalesTag({ info, active }) {
  const tone = active ? 'text-stage/80' : 'text-chalk-soft'
  const lines = info.status === 'ok' ? [`${info.sales_30d} sales · ${info.source}`]
    : info.status === 'low' ? [`Low data · ${info.sales_30d}`, info.source]
    : info.status === 'none' ? []                 // the price spot already says "No recent sales"
    : [info.source]                               // counts unavailable
  if (info.status !== null) lines.push(lastSoldText(info, true))
  return lines.filter(Boolean).map((line, i) => (
    <span key={i} className={`block text-[11px] leading-tight ${i === 0 ? 'mt-1' : ''} ${tone}`}>{line}</span>
  ))
}

// Price by grade (PSA 10, CGC 9.5 ...): eBay sales of graded copies, from data the page already loads.
// Same honesty rules as conditions: no sale in 30 days = "No recent sales" (with the last sale), and
// fewer than 10 sales ever = "Low data". Counts are PokeTrace's lifetime totals, marked as approximate.
function GradedPrices({ grades }) {
  const companies = [...new Set(grades.map(g => g.company))]
  return (
    <section aria-labelledby="graded-heading" className="glass rounded-panel p-5 sm:p-6">
      <h2 id="graded-heading" className="font-semibold">Price by grade</h2>
      <p className="mt-1 text-xs text-chalk-soft">
        eBay sales of graded copies. A price shows only if that grade sold in the last 30 days; sale counts are
        lifetime totals and approximate.
      </p>
      <div className="mt-4 space-y-4">
        {companies.map(company => (
          <div key={company}>
            <h3 className="text-sm font-semibold text-chalk-soft">{company}</h3>
            <ul className="mt-2 flex gap-2 overflow-x-auto -mx-1 px-1 pb-1">
              {grades.filter(g => g.company === company).map(g => (
                <li key={g.key} className="shrink-0 w-[7.5rem] rounded-chip bg-chalk/[0.06] px-3 py-2.5">
                  <span className="block text-xs text-chalk-soft">{company} {g.grade}</span>
                  <span className={`block mt-0.5 font-bold tabular-nums ${g.status === 'low' ? 'opacity-70' : ''}`}>
                    {g.price != null ? money(g.price) : <span className="text-xs font-semibold">No recent sales</span>}
                  </span>
                  <span className="block mt-1 text-[11px] leading-tight text-chalk-soft">
                    {g.status === 'low' ? 'Low data · ' : ''}{g.approx ? '~' : ''}{g.sales_ever} sold ever
                  </span>
                  {g.last_sold && (
                    <span className="block text-[11px] leading-tight text-chalk-soft">
                      {g.status === 'none' ? `Last ${money(g.last_price)} · ` : 'Last sold '}{dayLabel(g.last_sold, g.status === 'none' ? undefined : { month: 'short', day: 'numeric' })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}

function Stats({ history, currentPrice, now }) {
  if (!history || history.length < 2) return null
  const sorted = [...history].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at))
  const latest = currentPrice ?? sorted[sorted.length - 1].price
  const stats = [
    { label: '7 days', value: changeOver(sorted, latest, 7, now) },
    { label: '30 days', value: changeOver(sorted, latest, 30, now) },
    { label: '90 days', value: changeOver(sorted, latest, 90, now) },
  ]
  const high = Math.max(...sorted.map(h => h.price))

  return (
    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3 mt-5 pt-5 border-t border-chalk/10">
      {stats.map(s => (
        <div key={s.label}>
          <dt className="text-xs text-chalk-soft">{s.label}</dt>
          <dd className="mt-0.5 text-base">
            {s.value == null ? <span className="text-chalk-soft">—</span> : <Change value={s.value} />}
          </dd>
        </div>
      ))}
      <div>
        <dt className="text-xs text-chalk-soft">Highest</dt>
        <dd className="mt-0.5 text-base font-bold tabular-nums">{money(high)}</dd>
      </div>
    </dl>
  )
}

function PriceChart({ points }) {
  const line = token('--color-chalk')
  const faint = token('--color-chalk-soft')
  const data = {
    labels: points.map(h => new Date(h.recorded_at).toLocaleDateString()),
    datasets: [{
      label: 'Price',
      data: points.map(h => h.price),
      borderColor: line,
      borderWidth: 1.75,
      fill: false,
      tension: 0.25,
      pointRadius: 0,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: line,
      pointHoverBorderColor: token('--color-stage'),
    }],
  }
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : undefined,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: line,
        titleColor: token('--color-stage'),
        bodyColor: token('--color-stage'),
        displayColors: false,
        padding: 10,
        callbacks: { label: ctx => money(ctx.parsed.y) },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        border: { color: token('--color-chalk', 0.15) },
        ticks: { color: faint, maxTicksLimit: 5, maxRotation: 0, font: { family: 'Manrope' } },
      },
      y: {
        grid: { color: token('--color-chalk', 0.07) },
        border: { display: false },
        ticks: { color: faint, maxTicksLimit: 5, font: { family: 'Manrope' }, callback: v => `$${v}` },
      },
    },
  }
  return (
    <div className="h-56 sm:h-72" role="img" aria-label={`Price chart, ${points.length} data points`}>
      <Line data={data} options={options} />
    </div>
  )
}

function Skeleton() {
  return (
    <div className="grid lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] gap-6 lg:gap-10" aria-hidden="true">
      <div className="rounded-panel shimmer aspect-[4/5]" />
      <div className="space-y-4">
        <div className="h-10 w-2/3 rounded-chip shimmer" />
        <div className="h-5 w-1/3 rounded-chip shimmer" />
        <div className="h-14 w-1/2 rounded-chip shimmer" />
        <div className="h-72 rounded-panel shimmer" />
      </div>
    </div>
  )
}

function CardDetail() {
  const { poketraceId, productId } = useParams()
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [card, setCard] = useState(null)
  const [failed, setFailed] = useState(false)
  const [history, setHistory] = useState([])
  const [signal, setSignal] = useState(null)
  const [existingAlerts, setExistingAlerts] = useState([])
  const [chartRange, setChartRange] = useState('1m')
  const [condition, setCondition] = useState('NEAR_MINT')
  const [condData, setCondData] = useState(null)
  const [condPrices, setCondPrices] = useState({}) // condition → price, filled as each one loads
  const [reloadKey, setReloadKey] = useState(0)    // bump to re-check the watchlist after add/remove
  const [now] = useState(() => Date.now())

  const [showAddModal, setShowAddModal] = useState(false)
  const [addForm, setAddForm] = useState({ quantity: 1, price_paid: '', priority: 'normal', condition: 'NEAR_MINT' })
  const [showAlertModal, setShowAlertModal] = useState(false)
  const [alertForm, setAlertForm] = useState({ alert_type: 'above', threshold: '' })

  function loadAlerts(id) {
    if (!ALERTS_ENABLED) return
    apiFetch(`/alerts/${id}`)
      .then(res => res.json())
      .then(data => setExistingAlerts(data.alerts || []))
      .catch(() => setExistingAlerts([]))
  }

  // Load the card: a logged-in user's saved watchlist card uses their own price history
  // (same as clicking it on the old Market page); anything else uses the public PokeTrace view.
  useEffect(() => {
    if (authLoading) return
    if (productId ? !isProductId(productId) : !isPoketraceId(poketraceId)) return
    let cancelled = false

    async function load() {
      if (user) {
        try {
          const res = await apiFetch('/all-cards')
          const data = res.status === 401 ? null : await res.json()
          const saved = (data?.cards || []).find(c =>
            productId ? String(c.id) === productId : c.poketrace_id === poketraceId)
          if (saved) {
            if (cancelled) return
            setCard(saved)
            apiFetch(`/price-history/${saved.id}`)
              .then(res => res.json())
              .then(d => { if (!cancelled) setHistory(d.history || []) })
            apiFetch(`/signal/${saved.id}`)
              .then(res => res.json())
              .then(d => { if (!cancelled) setSignal(d) })
            loadAlerts(saved.id)
            return
          }
        } catch {
          // Couldn't read the watchlist — fall through to the public view
        }
      }

      if (!poketraceId) { if (!cancelled) setFailed(true); return }
      try {
        const res = await apiFetch(`/public-card/${encodeURIComponent(poketraceId)}`)
        const data = await res.json()
        if (cancelled) return
        if (!res.ok || data.error) { setFailed(true); return }
        setCard({
          id: null,
          poketrace_id: data.poketrace_id,
          name: data.name,
          set_name: data.set_name,
          image_url: data.image_url,
          latest_price: data.current_price,
          is_limited: data.is_limited,
        })
        setHistory(data.history || [])
        setSignal(null)
        setExistingAlerts([])
      } catch {
        if (!cancelled) setFailed(true)
      }
    }

    load()
    return () => { cancelled = true }
  }, [user, authLoading, poketraceId, productId, reloadKey])

  // Price + recent sales for the chosen condition
  useEffect(() => {
    if (!card?.poketrace_id) return
    let cancelled = false
    apiFetch(`/card-prices/${encodeURIComponent(card.poketrace_id)}?condition=${condition}`)
      .then(res => res.json())
      .then(data => {
        if (cancelled) return
        setCondData(data)
        // The API returns every condition's price at once; older API versions only send this one
        if (data?.prices && typeof data.prices === 'object' && Object.keys(data.prices).length) setCondPrices(data.prices)
        else if (data?.price != null) setCondPrices(p => ({ ...p, [condition]: data.price }))
      })
      .catch(() => { if (!cancelled) setCondData(null) })
    return () => { cancelled = true }
  }, [card?.poketrace_id, condition])

  function saveToWatchlist() {
    if (!user) { alert('Log in or create an account to save cards.'); return }
    apiFetch(`/save-card-poketrace/${encodeURIComponent(card.poketrace_id)}`)
      .then(res => res.json())
      .then(() => setReloadKey(k => k + 1))
  }

  function removeFromWatchlist() {
    if (!confirm('Remove this card from your watchlist?')) return
    apiFetch(`/delete-card/${card.id}`, { method: 'DELETE' })
      .then(() => {
        // Saved-only cards (no PokeTrace id) have no public page to fall back to
        if (!card.poketrace_id) navigate('/')
        else if (productId) navigate(`/card/${card.poketrace_id}`, { replace: true })
        else setReloadKey(k => k + 1)
      })
  }

  async function addToCollection() {
    if (!card) return

    let id = card.id

    // Fresh search result has no product id yet — save it first
    if (!id) {
      try {
        const saveRes = await apiFetch(`/save-card-poketrace/${encodeURIComponent(card.poketrace_id)}?watchlist=0`)
        const saved = await saveRes.json()
        id = saved.product_id
        if (!id) { alert('Could not save this card. Please try again.'); return }
      } catch {
        alert('Could not save this card. Please try again.')
        return
      }
    }

    try {
      const res = await apiFetch(`/add-to-collection/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity: parseInt(addForm.quantity) || 1,
          // Blank = "I don't know what I paid" (not $0), so it stays out of P&L
          price_paid: addForm.price_paid.trim() === '' ? null : parseFloat(addForm.price_paid),
          priority: addForm.priority,
          condition: addForm.condition
        })
      })
      const result = await res.json()
      if (result.success) {
        setShowAddModal(false)
        setAddForm({ quantity: 1, price_paid: '', priority: 'normal', condition: 'NEAR_MINT' })
        alert(`Added ${card.name} to your collection!`)
      } else {
        alert(result.error || 'Could not add to collection.')
      }
    } catch {
      alert('Could not add to collection.')
    }
  }

  function createAlert() {
    if (!card || !alertForm.threshold) return

    apiFetch(`/create-alert/${card.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alert_type: alertForm.alert_type,
        threshold: parseFloat(alertForm.threshold) || 0
      })
    })
      .then(() => {
        setShowAlertModal(false)
        setAlertForm({ alert_type: 'above', threshold: '' })
        loadAlerts(card.id)
      })
  }

  function deleteAlert(alertId) {
    if (!confirm('Delete this alert?')) return
    apiFetch(`/delete-alert/${alertId}`, { method: 'DELETE' })
      .then(() => loadAlerts(card.id))
  }

  function goBack() {
    // react-router keeps a history index; 0 means this page was opened directly (shared link)
    if (window.history.state?.idx > 0) navigate(-1)
    else navigate('/')
  }

  // Escape closes the card, like a pop-up. Skipped while a pop-up is open (it handles Escape
  // itself) and while typing or choosing in a field (Escape there means "cancel the field").
  const goBackRef = useRef(goBack)
  useEffect(() => { goBackRef.current = goBack })
  const modalOpen = showAddModal || showAlertModal
  useEffect(() => {
    if (modalOpen) return
    const onKey = e => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (e.target.closest?.('input, select, textarea, [contenteditable]')) return
      goBackRef.current()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [modalOpen])

  // Malformed link: don't send it anywhere
  if (productId ? !isProductId(productId) : !isPoketraceId(poketraceId)) {
    return <NotAvailable text="This card link doesn't look right. Try searching for the card instead." />
  }
  // A saved-card link needs the owner's watchlist
  if (productId && !authLoading && !user) {
    return <NotAvailable text="Log in to see this card from your watchlist." />
  }
  if (failed) {
    return <NotAvailable text="We couldn't load this card. It may have been removed, or the price service is busy." />
  }

  // Chart range
  const ranges = user ? RANGES : RANGES.filter(r => PUBLIC_RANGES.includes(r.key))
  const days = RANGES.find(r => r.key === chartRange)?.days ?? 30
  const filteredHistory = days === Infinity
    ? history
    : history.filter(h => new Date(h.recorded_at).getTime() >= now - days * 86400000)
  const rangeChange = filteredHistory.length >= 2 && filteredHistory[0].price
    ? ((filteredHistory[filteredHistory.length - 1].price - filteredHistory[0].price) / filteredHistory[0].price) * 100
    : null
  const rangePhrase = RANGES.find(r => r.key === chartRange)?.phrase

  // Honest prices: each condition comes with its 30-day TCGplayer sale count and a status
  // (ok / low / none; null when sale counts aren't available right now). See /card-prices in app.py.
  const condInfo = condData?.conditions?.[condition]
  const shownPrice = condData ? condData.price : (condition === 'NEAR_MINT' ? card?.latest_price : null)
  const signalLabel = signal?.signal ? signal.signal.charAt(0) + signal.signal.slice(1).toLowerCase() : null

  return (
    <div className="max-w-6xl mx-auto">
      {/* Sticks under the header so there's always a way out, however far down you scroll */}
      <div className="sticky top-[65px] md:top-[81px] z-20 -mx-4 px-4 py-2 mb-4 flex items-center justify-between pointer-events-none">
        <button type="button" onClick={goBack}
          className="pointer-events-auto inline-flex items-center gap-1.5 pl-3 pr-4 h-10 rounded-full bg-stage-raised border border-chalk/10 shadow-float text-sm font-semibold text-chalk-soft hover:text-chalk transition-colors">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4" aria-hidden="true">
            <path d="M15 18l-6-6 6-6" />
          </svg>
          Back
        </button>
        <button type="button" onClick={goBack} aria-label="Close card" title="Close (Esc)"
          className="pointer-events-auto w-10 h-10 rounded-full bg-stage-raised border border-chalk/10 shadow-float flex items-center justify-center text-chalk-soft hover:text-chalk transition-colors">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="w-4 h-4" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      {!card ? <Skeleton /> : (
        <div className="grid lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] gap-6 lg:gap-10 items-start">
          {/* ── Big card art ── */}
          <div className="glass rounded-panel p-8 sm:p-10 flex justify-center lg:sticky lg:top-28">
            <CardImage src={card.image_url} alt={card.name} className="w-full max-w-[17rem] sm:max-w-[19rem] shadow-float" />
          </div>

          <div className="min-w-0 space-y-6">
            {/* ── Name + price ── */}
            <header>
              <h1 className="font-display text-3xl sm:text-4xl font-semibold leading-tight tracking-tight break-words">{card.name}</h1>
              <p className="mt-1 text-chalk-soft">{card.set_name}</p>

              <div className="mt-5 flex flex-wrap items-end gap-x-4 gap-y-2">
                <p className="font-display text-4xl sm:text-5xl font-semibold tabular-nums">
                  {shownPrice != null ? money(shownPrice)
                    : <span className="text-2xl text-chalk-soft">{condInfo?.status === 'none' ? 'No recent sales' : 'No price'}</span>}
                </p>
                <p className="pb-1.5 text-sm text-chalk-soft">{conditionLabel(condition)}</p>
              </div>
              {condInfo && <PriceBasis info={condInfo} countsAvailable={condData?.counts_available} />}

              {signal?.signal && (
                <p className="mt-3 text-sm text-chalk-soft">
                  <span className="inline-block mr-2 px-3 py-1 rounded-full bg-chalk/[0.07] text-chalk font-semibold">{signalLabel}</span>
                  {signal.reason}
                  {signal.change_pct !== undefined && (
                    <> <Change value={signal.change_pct} /> overall</>
                  )}
                </p>
              )}
            </header>

            {/* ── Condition: black pill picker + price-per-condition strip ── */}
            {card.poketrace_id && (
              <section aria-labelledby="cond-heading" className="glass rounded-panel p-5 sm:p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 id="cond-heading" className="font-semibold">Condition</h2>
                  <div className="relative">
                    <label htmlFor="cond-select" className="sr-only">Condition</label>
                    <select id="cond-select" value={condition} onChange={e => setCondition(e.target.value)}
                      className="appearance-none bg-chalk text-stage rounded-full pl-5 pr-10 py-2.5 text-sm font-semibold cursor-pointer">
                      {CONDITIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                      className="absolute right-4 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-stage pointer-events-none" aria-hidden="true">
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </div>
                </div>

                <ul className="mt-4 flex sm:grid sm:grid-cols-5 gap-2 overflow-x-auto -mx-1 px-1 pb-1">
                  {CONDITIONS.map(c => {
                    const active = c.value === condition
                    const price = condPrices[c.value]
                    const info = condData?.conditions?.[c.value]
                    return (
                      <li key={c.value} className="shrink-0 w-[7.5rem] sm:w-auto">
                        <button type="button" onClick={() => setCondition(c.value)} aria-pressed={active}
                          className={`w-full h-full text-left rounded-chip px-3 py-2.5 transition-colors ${
                            active ? 'bg-chalk text-stage' : 'bg-chalk/[0.06] hover:bg-chalk/10 text-chalk'}`}>
                          <span className={`block text-xs ${active ? 'text-stage/80' : 'text-chalk-soft'}`}>{c.label}</span>
                          <span className={`block mt-0.5 font-bold tabular-nums ${info?.status === 'low' ? 'opacity-70' : ''}`}>
                            {price != null ? money(price) : info?.status === 'none' ? <span className="text-xs font-semibold">No recent sales</span> : '—'}
                          </span>
                          {info && <SalesTag info={info} active={active} />}
                        </button>
                      </li>
                    )
                  })}
                </ul>
                <p className="mt-3 text-xs text-chalk-soft">
                  {condData?.counts_available === false
                    ? 'TCGplayer prices. Sale counts are unavailable right now, so these prices are not checked against recent sales.'
                    : `Prices from TCGplayer, or eBay when only eBay has sold that condition lately (always labelled). Sales = last ${condData?.window_days || 30} days; "Low data" = fewer than ${condData?.low_data_below || 10}.`}
                </p>
              </section>
            )}

            {condData?.graded?.length > 0 && <GradedPrices grades={condData.graded} />}

            {/* ── Actions ── */}
            <div className="space-y-3">
              <button type="button" className={`${btn.primary} w-full py-4 text-base`}
                onClick={() => user ? setShowAddModal(true) : alert('Log in or create an account to add cards to your collection.')}>
                Add to collection
              </button>

              <div className={`grid grid-cols-1 gap-3 ${ALERTS_ENABLED ? 'sm:grid-cols-2' : ''}`}>
                {card.id ? (
                  <button type="button" className={btn.secondary} onClick={removeFromWatchlist}>
                    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4" aria-hidden="true"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" /></svg>
                    Remove from watchlist
                  </button>
                ) : (
                  <button type="button" className={btn.secondary} onClick={saveToWatchlist} disabled={!card.poketrace_id}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-4 h-4" aria-hidden="true"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" /></svg>
                    Add to watchlist
                  </button>
                )}

                {ALERTS_ENABLED && (
                  <button type="button" className={btn.secondary}
                    disabled={!!user && !card.id}
                    onClick={() => user ? setShowAlertModal(true) : alert('Log in or create an account to set price alerts.')}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="w-4 h-4" aria-hidden="true"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" /></svg>
                    Discord price alert
                  </button>
                )}
              </div>
              {ALERTS_ENABLED && user && !card.id && (
                <p className="text-xs text-chalk-soft">Add this card to your watchlist to set a Discord price alert.</p>
              )}

              {existingAlerts.length > 0 && (
                <div className="glass rounded-panel p-4">
                  <p className="text-sm font-semibold mb-2">Your alerts</p>
                  <ul className="divide-y divide-chalk/10">
                    {existingAlerts.map(a => (
                      <li key={a.id} className="flex items-center justify-between py-2 text-sm">
                        <span className="tabular-nums">
                          {a.alert_type === 'above' ? 'Rises above' : a.alert_type === 'below' ? 'Drops below' : 'Changes by'} ${a.threshold}
                        </span>
                        <button type="button" onClick={() => deleteAlert(a.id)} className={btn.danger}>Remove</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* ── Price history ── */}
            <section aria-labelledby="history-heading" className="glass rounded-panel p-5 sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div>
                  <h2 id="history-heading" className="font-semibold">Price history</h2>
                  {rangeChange != null && (
                    <p className="text-sm text-chalk-soft"><Change value={rangeChange} /> {rangePhrase}</p>
                  )}
                </div>
                <div className="flex gap-1 p-1 rounded-full bg-chalk/[0.05]" role="group" aria-label="Chart range">
                  {ranges.map(r => (
                    <button key={r.key} type="button" onClick={() => setChartRange(r.key)}
                      aria-pressed={chartRange === r.key} className={chip(chartRange === r.key)}>
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              {filteredHistory.length >= 2 ? (
                <PriceChart points={filteredHistory} />
              ) : (
                <p className="text-chalk-soft text-center py-12 text-sm">
                  {history.length < 2
                    ? 'Not enough price history yet. Needs at least 2 data points.'
                    : `Not enough data ${rangePhrase}. Try a longer range.`}
                </p>
              )}

              <Stats history={history} currentPrice={card.latest_price} now={now} />

              {card.is_limited && (
                <p className="mt-5 text-sm text-chalk-soft">
                  Showing the last 30 days. <Link to="/signup" className="font-semibold text-chalk underline underline-offset-4">Create an account</Link> to see the full price history.
                </p>
              )}
            </section>

            {/* ── Recent sales ── */}
            {condData?.sales?.length > 0 && (
              <section aria-labelledby="sales-heading" className="glass rounded-panel p-5 sm:p-6">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h2 id="sales-heading" className="font-semibold">Recent sales</h2>
                  <span className="text-xs font-semibold px-3 py-1 rounded-full bg-chalk/[0.07]">{conditionLabel(condition)}</span>
                </div>
                <div className="overflow-x-auto -mx-2">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-chalk-soft">
                        <th scope="col" className="font-semibold px-2 py-2">Date</th>
                        <th scope="col" className="font-semibold px-2 py-2">Sales</th>
                        <th scope="col" className="font-semibold px-2 py-2 text-right">Sold for</th>
                        <th scope="col" className="font-semibold px-2 py-2">Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {condData.sales.map((s, i) => (
                        <tr key={i} className="border-t border-chalk/10">
                          {/* "2026-10-23" is a calendar day, not a moment: read as UTC midnight it showed as
                              Oct 22 in US time zones. Formatting it in UTC keeps the day PokeTrace meant. */}
                          <td className="px-2 py-2.5 whitespace-nowrap">{new Date(s.date).toLocaleDateString(undefined, { timeZone: 'UTC' })}</td>
                          <td className="px-2 py-2.5 tabular-nums">{s.sale_count}</td>
                          <td className="px-2 py-2.5 text-right font-bold tabular-nums whitespace-nowrap">
                            {/* low/high are that day's real sale prices. PokeTrace's "avg" is a smoothed running
                                price, so it isn't shown here (a $11.16 sale used to show as $13.49). */}
                            {saleAmount(s)}
                          </td>
                          <td className="px-2 py-2.5 text-chalk-soft">{sourceName(s.source)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </div>
        </div>
      )}

      {showAddModal && (
        <Modal title="Add to collection" subtitle={`${card?.name}, ${card?.set_name}`} onClose={() => setShowAddModal(false)}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="add-qty" className={label}>Quantity</label>
                <input id="add-qty" type="number" min="1" value={addForm.quantity}
                  onChange={e => setAddForm({ ...addForm, quantity: e.target.value })} className={field} />
              </div>
              <div>
                <label htmlFor="add-paid" className={label}>Price paid (each)</label>
                <input id="add-paid" type="number" step="0.01" min="0" placeholder="Optional" value={addForm.price_paid}
                  onChange={e => setAddForm({ ...addForm, price_paid: e.target.value })} className={field} />
              </div>
            </div>
            <div>
              <label htmlFor="add-cond" className={label}>Condition</label>
              <select id="add-cond" value={addForm.condition}
                onChange={e => setAddForm({ ...addForm, condition: e.target.value })} className={field}>
                {CONDITIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="add-priority" className={label}>Priority</label>
              <select id="add-priority" value={addForm.priority}
                onChange={e => setAddForm({ ...addForm, priority: e.target.value })} className={field}>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>
          <div className="flex gap-3 mt-6">
            <button type="button" onClick={() => setShowAddModal(false)} className={`${btn.secondary} flex-1`}>Cancel</button>
            <button type="button" onClick={addToCollection} className={`${btn.primary} flex-1`}>Add</button>
          </div>
        </Modal>
      )}

      {showAlertModal && (
        <Modal title="Discord price alert" subtitle={`${card?.name}, ${card?.set_name}`} onClose={() => setShowAlertModal(false)}>
          <div className="space-y-4">
            <div>
              <label htmlFor="alert-type" className={label}>Alert me when the price</label>
              <select id="alert-type" value={alertForm.alert_type}
                onChange={e => setAlertForm({ ...alertForm, alert_type: e.target.value })} className={field}>
                <option value="above">Rises to</option>
                <option value="below">Drops to</option>
              </select>
            </div>
            <div>
              <label htmlFor="alert-threshold" className={label}>Price ($)</label>
              <input id="alert-threshold" type="number" step="0.01" placeholder="400.00" value={alertForm.threshold}
                onChange={e => setAlertForm({ ...alertForm, threshold: e.target.value })} className={field} />
            </div>
          </div>
          <div className="flex gap-3 mt-6">
            <button type="button" onClick={() => setShowAlertModal(false)} className={`${btn.secondary} flex-1`}>Cancel</button>
            <button type="button" onClick={createAlert} className={`${btn.primary} flex-1`}>Create alert</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function NotAvailable({ text }) {
  return (
    <div className="max-w-md mx-auto text-center glass rounded-panel p-10 my-10">
      <h1 className="font-display text-2xl font-semibold">Card not available</h1>
      <p className="mt-3 text-chalk-soft">{text}</p>
      <Link to="/" className={`${btn.primary} mt-6`}>Back to Market</Link>
    </div>
  )
}

// Remount on every card URL so one card's state never leaks into the next
export default function CardDetailPage() {
  const { pathname } = useLocation()
  return <CardDetail key={pathname} />
}
