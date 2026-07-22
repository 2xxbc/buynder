import { useState, useEffect } from 'react';
import { apiFetch } from '../config';
function CardSearch({
  onAdd
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    const timeout = setTimeout(() => {
      apiFetch(`/poketrace-search/${encodeURIComponent(query)}`).then(res => res.json()).then(data => {
        setResults(data.results || []);
        setSearching(false);
      }).catch(() => setSearching(false));
    }, 400);
    return () => clearTimeout(timeout);
  }, [query]);
  function choose(r) {
    onAdd({
      poketrace_id: r.poketrace_id,
      name: r.name,
      set_name: r.set_name,
      image: r.image,
      display_price: r.display_price
    });
    setQuery('');
    setResults([]);
  }
  return <div className="relative">
      <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search a card to add…" className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm" />
      {searching && <p className="text-xs text-slate-500 mt-1">Searching…</p>}
      {results.length > 0 && <div className="absolute z-20 left-0 right-0 mt-1 bg-slate-900 border border-slate-700 rounded-lg max-h-56 overflow-y-auto shadow-xl">
          {results.map(r => <button key={r.poketrace_id} onClick={() => choose(r)} className="w-full text-left px-3 py-2 hover:bg-slate-800 flex items-center gap-2 border-b border-slate-800 last:border-0">
              <img src={r.image} alt={r.name} className="w-7 rounded" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{r.name}</p>
                <p className="text-xs text-slate-400 truncate">{r.set_name} · {r.number}</p>
              </div>
              <span className="text-xs text-slate-400">${r.display_price}</span>
            </button>)}
        </div>}
    </div>;
}
function BundleSide({
  title,
  cards,
  setCards
}) {
  function addCard(card) {
    setCards([...cards, {
      ...card,
      agreed_value: ''
    }]);
  }
  function removeCard(idx) {
    setCards(cards.filter((_, i) => i !== idx));
  }
  function setValue(idx, val) {
    setCards(cards.map((c, i) => i === idx ? {
      ...c,
      agreed_value: val
    } : c));
  }
  const total = cards.reduce((sum, c) => sum + (parseFloat(c.agreed_value) || 0), 0);
  return <div className="bg-slate-900/50 rounded-xl border border-slate-700 p-4">
      <h4 className="font-semibold mb-3">{title}</h4>
      <CardSearch onAdd={addCard} />
      <div className="mt-3 space-y-2">
        {cards.length === 0 && <p className="text-xs text-slate-500">No cards added yet.</p>}
        {cards.map((c, idx) => <div key={idx} className="flex items-center gap-2 bg-slate-800 rounded-lg p-2">
            <img src={c.image} alt={c.name} className="w-8 rounded" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{c.name}</p>
              <p className="text-xs text-slate-400 truncate">{c.set_name} · mkt ${c.display_price}</p>
            </div>
            <input type="number" placeholder="value $" value={c.agreed_value} onChange={e => setValue(idx, e.target.value)} className="w-24 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white text-sm" />
            <button onClick={() => removeCard(idx)} className="text-slate-500 hover:text-red-400 px-1">✕</button>
          </div>)}
      </div>
      {cards.length > 0 && <p className="text-sm text-slate-400 mt-3 text-right">Agreed total: <span className="text-white font-semibold">${total.toFixed(2)}</span></p>}
    </div>;
}
function Trades() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [gaveCards, setGaveCards] = useState([]);
  const [gotCards, setGotCards] = useState([]);
  const [cashDirection, setCashDirection] = useState('none');
  const [cashAmount, setCashAmount] = useState('');
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  useEffect(() => {
    loadTrades();
  }, []);
  function loadTrades() {
    apiFetch('/trades').then(res => res.json()).then(data => {
      setTrades(data.trades || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }
  async function ensureCard(card) {
    const res = await apiFetch(`/save-card-poketrace/${encodeURIComponent(card.poketrace_id)}?watchlist=0`);
    const data = await res.json();
    return data.product_id || null;
  }
  function resetForm() {
    setGaveCards([]);
    setGotCards([]);
    setCashDirection('none');
    setCashAmount('');
    setTradeDate(new Date().toISOString().slice(0, 10));
    setNotes('');
  }
  async function submitTrade() {
    if (gaveCards.length === 0 || gotCards.length === 0) {
      alert('Add at least one card on each side.');
      return;
    }
    setSaving(true);
    try {
      const gavePayload = [];
      for (const c of gaveCards) {
        const pid = await ensureCard(c);
        gavePayload.push({
          product_id: pid,
          name: c.name,
          agreed_value: parseFloat(c.agreed_value) || 0
        });
      }
      const gotPayload = [];
      for (const c of gotCards) {
        const pid = await ensureCard(c);
        gotPayload.push({
          product_id: pid,
          name: c.name,
          agreed_value: parseFloat(c.agreed_value) || 0
        });
      }
      const res = await apiFetch('/log-trade', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          trade_date: tradeDate,
          cash_amount: parseFloat(cashAmount) || 0,
          cash_direction: cashDirection,
          notes,
          gave: gavePayload,
          got: gotPayload
        })
      });
      const data = await res.json();
      if (data.success) {
        setShowForm(false);
        resetForm();
        loadTrades();
      } else {
        alert(data.error || 'Failed to log trade');
      }
    } catch (e) {
      alert('Something went wrong saving the trade.');
    } finally {
      setSaving(false);
    }
  }
  function deleteTrade(id) {
    if (!confirm('Delete this trade record?')) return;
    apiFetch(`/delete-trade/${id}`, {
      method: 'DELETE'
    }).then(() => loadTrades());
  }
  function pctColor(pct) {
    if (pct === null || pct === undefined) return 'text-slate-400';
    return pct >= 0 ? 'text-green-400' : 'text-red-400';
  }
  const fmtPct = p => p === null || p === undefined ? '—' : `${p >= 0 ? '+' : ''}${p}%`;
  const fmtMoney = v => v === null || v === undefined ? '—' : `$${v}`;
  return <>
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-3xl font-bold">Trades</h2>
        <button onClick={() => {
        setShowForm(!showForm);
        if (showForm) resetForm();
      }} className="bg-red-500 hover:bg-red-600 text-white font-semibold px-4 py-2 rounded-lg transition-colors">
          {showForm ? 'Cancel' : '+ Log a Trade'}
        </button>
      </div>

      {showForm && <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-10">
          <h3 className="text-xl font-semibold mb-4">Log a Trade</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <BundleSide title="Cards you gave away" cards={gaveCards} setCards={setGaveCards} />
            <BundleSide title="Cards you received" cards={gotCards} setCards={setGotCards} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Cash involved?</label>
              <div className="flex gap-2">
                <select value={cashDirection} onChange={e => setCashDirection(e.target.value)} className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white">
                  <option value="none">No cash</option>
                  <option value="paid">I paid cash</option>
                  <option value="received">I got cash</option>
                </select>
                <input type="number" placeholder="0.00" value={cashAmount} disabled={cashDirection === 'none'} onChange={e => setCashAmount(e.target.value)} className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white disabled:opacity-40" />
              </div>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Trade date</label>
              <input type="date" value={tradeDate} onChange={e => setTradeDate(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white" />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Notes</label>
              <input type="text" placeholder="e.g. league night" value={notes} onChange={e => setNotes(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white" />
            </div>
          </div>
          <button onClick={submitTrade} disabled={saving} className="mt-5 bg-green-500 hover:bg-green-600 disabled:opacity-50 text-white font-semibold px-5 py-2 rounded-lg transition-colors">
            {saving ? 'Saving…' : 'Save Trade'}
          </button>
        </div>}

      {loading ? <p className="text-slate-400">Loading...</p> : trades.length === 0 ? <p className="text-slate-400 text-center py-20">No trades logged yet. Click "+ Log a Trade" to record one.</p> : <div className="space-y-4">
          {trades.map(t => <div key={t.id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
              <div className="flex items-start justify-between mb-3">
                <div className="text-sm text-slate-400">{new Date(t.trade_date).toLocaleDateString()}</div>
                <div className="flex items-center gap-4">
                  <div className={`text-right font-bold text-lg ${pctColor(t.pct_now)}`}>
                    {fmtPct(t.pct_now)}
                    <span className="block text-xs font-normal text-slate-500">{fmtMoney(t.net_now)} live</span>
                  </div>
                  <button onClick={() => deleteTrade(t.id)} className="text-slate-500 hover:text-red-400 text-sm">Delete</button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Gave · market ${t.gave_market_total ?? '—'}</p>
                  {t.gave_cards.map((c, i) => <div key={i} className="flex justify-between text-sm py-1 border-b border-slate-700/50">
                      <span>{c.name}</span>
                      <span className="text-slate-400">agreed {fmtMoney(c.agreed)} · now {fmtMoney(c.market_now)}</span>
                    </div>)}
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Got · market ${t.got_market_total ?? '—'}</p>
                  {t.got_cards.map((c, i) => <div key={i} className="flex justify-between text-sm py-1 border-b border-slate-700/50">
                      <span>{c.name}</span>
                      <span className="text-slate-400">agreed {fmtMoney(c.agreed)} · now {fmtMoney(c.market_now)}</span>
                    </div>)}
                </div>
              </div>
              {t.cash_direction !== 'none' && <p className="text-sm text-slate-400 mt-3">
                  Cash: {t.cash_direction === 'paid' ? 'you paid' : 'you received'} ${t.cash_amount}
                </p>}
              {t.notes && <p className="text-sm text-slate-500 mt-1 italic">{t.notes}</p>}
            </div>)}
        </div>}
    </>;
}
export default Trades;
