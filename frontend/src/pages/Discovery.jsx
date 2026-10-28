import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { TRENDING } from '../names'
import { apiFetch } from '../config'
import CardImage from '../components/CardImage'
import Change from '../components/Change'
import { money } from '../components/ui'

function CardRow({ card, rank, metric, window }) {
  const pct = window === '7d' ? card.pct_7d : card.pct_30d
  return (
    <li>
      <Link to={`/card/${card.poketrace_id}`}
        className="flex items-center gap-3 p-2.5 rounded-[4px] hover:bg-chalk/5 transition-colors">
        <span className={`w-5 shrink-0 text-center text-xs font-bold tabular-nums ${rank === 1 ? 'text-volt' : 'text-chalk-soft'}`}>{rank}</span>
        <CardImage src={card.image_url} alt="" tone="dark" className="w-10" />
        <span className="flex-1 min-w-0">
          <span className="block font-semibold text-sm text-chalk truncate">{card.name}</span>
          <span className="block text-xs text-chalk-soft truncate">{card.set_name}</span>
        </span>
        <span className="text-right shrink-0 text-sm">
          {metric === 'volume' ? (
            <>
              {/* sold_window = sales in the last N days (daily snapshots); without it, lifetime sales */}
              <span className="block font-bold text-chalk tabular-nums">{(card.sold_window ?? card.sale_count).toLocaleString()}</span>
              <span className="block text-xs text-chalk-soft">sold</span>
            </>
          ) : (
            <>
              <Change value={pct} className="block" />
              <span className="block text-xs text-chalk-soft tabular-nums mt-0.5">{money(card.price)}</span>
            </>
          )}
        </span>
      </Link>
    </li>
  )
}

function Section({ title, subtitle, cards, metric, window }) {
  return (
    <section className="bg-stage-raised border border-stage-line rounded-[4px] p-4 sm:p-5">
      <div className="mb-3 px-1">
        <h2 className="font-display text-lg font-semibold text-chalk">{title}</h2>
        <p className="text-xs text-chalk-soft mt-0.5">{subtitle}</p>
      </div>
      {cards.length === 0
        ? <p className="text-sm text-chalk-soft text-center py-8">Not enough data for this filter.</p>
        : (
          <ol className="space-y-0.5">
            {cards.map((c, i) => (
              <CardRow key={c.poketrace_id} card={c} rank={i + 1} metric={metric} window={window} />
            ))}
          </ol>
        )}
    </section>
  )
}

function Discovery() {
  const [data, setData] = useState(null)
  const [sets, setSets] = useState([])
  const [setSlug, setSetSlug] = useState('')
  const [window, setWindow] = useState('30d')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    apiFetch('/market-sets')
      .then(res => res.json())
      .then(d => setSets(d.sets || []))
      .catch(() => {})
  }, [])

  // Changing a filter shows the loading state until the new numbers arrive
  function changeSet(slug) { setLoading(true); setSetSlug(slug) }
  function changeWindow(w) { if (w !== window) { setLoading(true); setWindow(w) } }

  useEffect(() => {
    const params = new URLSearchParams({ window })
    if (setSlug) params.set('set', setSlug)
    apiFetch(`/discovery?${params}`)
      .then(res => res.json())
      .then(d => {
        if (d.error) setError(d.error)
        else { setData(d); setError('') }
        setLoading(false)
      })
      .catch(() => { setError('Could not load market data.'); setLoading(false) })
  }, [setSlug, window])

  const label = window === '7d' ? '7-day' : '30-day'

  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-semibold tracking-tight text-chalk">{TRENDING}</h1>
        <p className="mt-3 text-chalk-soft">
          Biggest {label} changes
          {data?.cards_tracked ? ` across ${data.cards_tracked.toLocaleString()} cards` : ''}.
          {data?.last_synced && ` Updated ${new Date(data.last_synced).toLocaleDateString()}.`}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-8">
        <div className="relative w-full sm:w-auto">
          <label htmlFor="set-filter" className="sr-only">Filter by set</label>
          <select
            id="set-filter"
            value={setSlug}
            onChange={e => changeSet(e.target.value)}
            className="appearance-none w-full sm:w-72 bg-stage-raised border border-stage-line rounded-[4px] pl-4 pr-10 py-2.5 text-chalk text-sm font-semibold cursor-pointer focus:border-volt transition-colors"
          >
            <option value="">All sets</option>
            {sets.map(s => (
              <option key={s.set_slug} value={s.set_slug}>
                {s.set_name} ({s.card_count})
              </option>
            ))}
          </select>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
            className="absolute right-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-chalk-soft pointer-events-none" aria-hidden="true">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </div>

        <div className="flex gap-1 p-1 bg-stage-raised border border-stage-line rounded-[4px]" role="group" aria-label="Time window">
          {['7d', '30d'].map(w => (
            <button
              key={w}
              type="button"
              onClick={() => changeWindow(w)}
              aria-pressed={window === w}
              className={`px-4 py-1.5 text-sm font-semibold rounded-[3px] transition-colors ${
                window === w ? 'bg-volt text-stage' : 'text-chalk-soft hover:text-chalk hover:bg-chalk/5'
              }`}
            >
              {w === '7d' ? '7 days' : '30 days'}
            </button>
          ))}
        </div>

        {setSlug && (
          <button type="button" onClick={() => changeSet('')} className="text-sm text-chalk-soft hover:text-chalk font-semibold underline underline-offset-4">
            Clear filter
          </button>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" aria-hidden="true">
          {[0, 1, 2].map(i => <div key={i} className="h-96 rounded-[4px] shimmer" />)}
        </div>
      ) : error ? (
        <p className="text-down-bright text-center py-24" role="alert">{error}</p>
      ) : data ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Section title="Top gainers" subtitle={`Biggest ${label} increases`} cards={data.gainers} metric="pct" window={window} />
          <Section title="Top losers" subtitle={`Biggest ${label} drops`} cards={data.losers} metric="pct" window={window} />
          <Section title={data.volume_window_days ? `Most sold (${data.volume_window_days >= 30 ? '30 days' : `last ${data.volume_window_days} days`})` : 'Most sold (all time)'}
            subtitle={data.volume_window_days ? 'Near-mint TCGplayer sales, via PokeTrace' : 'Lifetime near-mint TCGplayer sales, via PokeTrace'}
            cards={data.volume} metric="volume" window={window} />
        </div>
      ) : null}

      <p className="text-xs text-chalk-soft mt-10 text-center max-w-lg mx-auto">
        Only cards priced $10+ with 50+ sales are ranked, so small moves on cheap cards don't skew the list.
      </p>
    </>
  )
}

export default Discovery
