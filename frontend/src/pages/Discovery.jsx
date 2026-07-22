import { useState, useEffect } from 'react';
import { apiFetch } from '../config';
function CardImage({
  src,
  alt
}) {
  const [broken, setBroken] = useState(false);
  if (!src || broken) {
    return <div className="w-10 h-14 rounded bg-slate-700 shrink-0 flex items-center justify-center text-slate-500 text-lg">
        ?
      </div>;
  }
  return <img src={src} alt={alt} onError={() => setBroken(true)} className="w-10 h-14 object-cover rounded shrink-0" />;
}
function Pct({
  value
}) {
  if (value === null || value === undefined) return <span className="text-slate-500">—</span>;
  const up = value >= 0;
  return <span className={`font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
      {up ? '+' : ''}{value}%
    </span>;
}
function CardRow({
  card,
  rank,
  metric,
  window
}) {
  const pct = window === '7d' ? card.pct_7d : card.pct_30d;
  return <div className="flex items-center gap-3 p-3 bg-slate-800 rounded-lg border border-slate-700 hover:border-amber-500 transition-colors">
      <span className="text-xs text-slate-500 w-5 shrink-0">{rank}</span>
      <CardImage src={card.image_url} alt={card.name} />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm truncate">{card.name}</p>
        <p className="text-xs text-slate-500 truncate">{card.set_name}</p>
      </div>
      <div className="text-right shrink-0">
        {metric === 'volume' ? <>
            <p className="font-bold text-sm text-amber-400">{card.sale_count.toLocaleString()}</p>
            <p className="text-xs text-slate-500">sales</p>
          </> : <>
            <p className="text-sm"><Pct value={pct} /></p>
            <p className="text-xs text-slate-500">${card.price}</p>
          </>}
      </div>
    </div>;
}
function Section({
  title,
  subtitle,
  cards,
  metric,
  window
}) {
  return <div>
      <div className="mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
      <div className="space-y-2">
        {cards.length === 0 ? <p className="text-sm text-slate-500">Not enough data for this filter.</p> : cards.map((c, i) => <CardRow key={c.poketrace_id} card={c} rank={i + 1} metric={metric} window={window} />)}
      </div>
    </div>;
}
function Discovery() {
  const [data, setData] = useState(null);
  const [sets, setSets] = useState([]);
  const [setSlug, setSetSlug] = useState('');
  const [window, setWindow] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    apiFetch('/market-sets').then(res => res.json()).then(d => setSets(d.sets || [])).catch(() => {});
  }, []);
  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({
      window
    });
    if (setSlug) params.set('set', setSlug);
    apiFetch(`/discovery?${params}`).then(res => res.json()).then(d => {
      if (d.error) setError(d.error);else {
        setData(d);
        setError('');
      }
      setLoading(false);
    }).catch(() => {
      setError('Could not load market data.');
      setLoading(false);
    });
  }, [setSlug, window]);
  const label = window === '7d' ? '7-day' : '30-day';
  return <>
      <div className="mb-6">
        <h2 className="text-3xl font-bold mb-2">Market Movers</h2>
        <p className="text-slate-400 text-sm">
          Biggest {label} changes
          {data?.cards_tracked ? ` across ${data.cards_tracked.toLocaleString()} cards` : ''}
          {data?.last_synced && <span className="text-slate-600"> · Updated {new Date(data.last_synced).toLocaleDateString()}</span>}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-8">
        <select value={setSlug} onChange={e => setSetSlug(e.target.value)} className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm max-w-xs">
          <option value="">All sets</option>
          {sets.map(s => <option key={s.set_slug} value={s.set_slug}>
              {s.set_name} ({s.card_count})
            </option>)}
        </select>

        <div className="flex gap-1 bg-slate-900 rounded-lg p-1">
          {['7d', '30d'].map(w => <button key={w} onClick={() => setWindow(w)} className={`px-4 py-1.5 text-xs font-semibold rounded transition-colors ${window === w ? 'bg-amber-500 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}>
              {w.toUpperCase()}
            </button>)}
        </div>

        {setSlug && <button onClick={() => setSetSlug('')} className="text-xs text-slate-400 hover:text-white">
            Clear filter
          </button>}
      </div>

      {loading ? <p className="text-slate-400 text-center py-24">Loading market data…</p> : error ? <p className="text-red-400 text-center py-24">{error}</p> : data ? <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <Section title="📈 Top Gainers" subtitle={`Biggest ${label} increases`} cards={data.gainers} metric="pct" window={window} />
          <Section title="📉 Top Losers" subtitle={`Biggest ${label} drops`} cards={data.losers} metric="pct" window={window} />
          <Section title="🔥 Most Traded" subtitle="Highest sales volume" cards={data.volume} metric="volume" window={window} />
        </div> : null}

      <p className="text-xs text-slate-600 mt-10 text-center">
        Only cards priced $10+ with 50+ sales are ranked, so small moves on cheap cards don't skew the list.
      </p>
    </>;
}
export default Discovery;
