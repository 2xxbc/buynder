import { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler } from 'chart.js';
import { API_URL, apiFetch } from '../config';
import { useAuth } from '../AuthContext';
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);
function StatsBar({
  history,
  currentPrice
}) {
  if (!history || history.length < 2) return null;
  const now = Date.now();
  const sorted = [...history].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));
  const latest = currentPrice ?? sorted[sorted.length - 1].price;
  function priceDaysAgo(days) {
    const target = now - days * 86400000;
    let closest = null;
    for (const h of sorted) {
      if (new Date(h.recorded_at).getTime() <= target) closest = h.price;
    }
    return closest;
  }
  function pct(days) {
    const past = priceDaysAgo(days);
    if (!past || past === 0) return null;
    return (latest - past) / past * 100;
  }
  const allTimeHigh = Math.max(...sorted.map(h => h.price));
  const stats = [{
    label: '7D',
    value: pct(7),
    isPct: true
  }, {
    label: '30D',
    value: pct(30),
    isPct: true
  }, {
    label: '90D',
    value: pct(90),
    isPct: true
  }, {
    label: 'High',
    value: allTimeHigh,
    isPct: false
  }];
  return <div className="grid grid-cols-4 gap-2 mb-4">
      {stats.map(s => <div key={s.label} className="bg-slate-900 rounded-lg p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">{s.label}</p>
          {s.value === null ? <p className="text-sm text-slate-600">—</p> : s.isPct ? <p className={`text-sm font-bold ${s.value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {s.value >= 0 ? '+' : ''}{s.value.toFixed(1)}%
            </p> : <p className="text-sm font-bold text-amber-400">${s.value.toFixed(2)}</p>}
        </div>)}
    </div>;
}
function Market() {
  const {
    user
  } = useAuth();
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedCard, setSelectedCard] = useState(null);
  const [history, setHistory] = useState([]);
  const [chartRange, setChartRange] = useState('1m');
  const [signal, setSignal] = useState(null);
  const [condition, setCondition] = useState('NEAR_MINT');
  const [condData, setCondData] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    quantity: 1,
    price_paid: '',
    priority: 'normal',
    condition: 'NEAR_MINT'
  });
  const [showAlertModal, setShowAlertModal] = useState(false);
  const [alertForm, setAlertForm] = useState({
    alert_type: 'above',
    threshold: ''
  });
  const [existingAlerts, setExistingAlerts] = useState([]);
  function loadCondition(poketraceId, cond) {
    apiFetch(`/card-prices/${encodeURIComponent(poketraceId)}?condition=${cond}`).then(res => res.json()).then(data => setCondData(data)).catch(() => setCondData(null));
  }
  useEffect(() => {
    if (selectedCard?.poketrace_id) {
      loadCondition(selectedCard.poketrace_id, condition);
    }
  }, [selectedCard?.poketrace_id, condition]);
  useEffect(() => {
    if (user) {
      loadCards();
    } else {
      setLoading(false);
    }
  }, [user]);
  function loadCards() {
    apiFetch('/all-cards').then(res => {
      if (res.status === 401) {
        return null;
      }
      return res.json();
    }).then(data => {
      if (data) setCards(data.cards || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }
  useEffect(() => {
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    const timeout = setTimeout(() => {
      apiFetch(`/poketrace-search/${encodeURIComponent(query)}`).then(res => res.json()).then(data => {
        setSearchResults(data.results || []);
        setSearching(false);
      }).catch(() => setSearching(false));
    }, 400);
    return () => clearTimeout(timeout);
  }, [query]);
  function saveCard(poketraceId) {
    apiFetch(`/save-card-poketrace/${encodeURIComponent(poketraceId)}`).then(res => res.json()).then(() => {
      setQuery('');
      setSearchResults([]);
      loadCards();
    });
  }
  function deleteCard(productId) {
    if (!confirm('Remove this card from your watchlist?')) return;
    apiFetch(`/delete-card/${productId}`, {
      method: 'DELETE'
    }).then(() => {
      if (selectedCard?.id === productId) setSelectedCard(null);
      loadCards();
    });
  }
  async function addToCollection() {
    if (!selectedCard) return;
    let productId = selectedCard.id;
    if (!productId) {
      try {
        const saveRes = await apiFetch(`/save-card-poketrace/${encodeURIComponent(selectedCard.poketrace_id)}?watchlist=0`);
        const saved = await saveRes.json();
        productId = saved.product_id;
        if (!productId) {
          alert('Could not save this card. Please try again.');
          return;
        }
      } catch {
        alert('Could not save this card. Please try again.');
        return;
      }
    }
    try {
      const res = await apiFetch(`/add-to-collection/${productId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          quantity: parseInt(addForm.quantity) || 1,
          price_paid: parseFloat(addForm.price_paid) || 0,
          priority: addForm.priority,
          condition: addForm.condition
        })
      });
      const result = await res.json();
      if (result.success) {
        setShowAddModal(false);
        setAddForm({
          quantity: 1,
          price_paid: '',
          priority: 'normal',
          condition: 'NEAR_MINT'
        });
        alert(`Added ${selectedCard.name} to your collection!`);
      } else {
        alert(result.error || 'Could not add to collection.');
      }
    } catch {
      alert('Could not add to collection.');
    }
  }
  function selectCard(card) {
    setSelectedCard(card);
    apiFetch(`/price-history/${card.id}`).then(res => res.json()).then(data => setHistory(data.history || []));
    apiFetch(`/signal/${card.id}`).then(res => res.json()).then(data => setSignal(data));
    loadAlerts(card.id);
  }
  function viewPublicCard(poketraceId) {
    setQuery('');
    setSearchResults([]);
    apiFetch(`/public-card/${encodeURIComponent(poketraceId)}`).then(res => res.json()).then(data => {
      setSelectedCard({
        id: null,
        poketrace_id: data.poketrace_id,
        name: data.name,
        set_name: data.set_name,
        image_url: data.image_url,
        latest_price: data.current_price,
        is_limited: data.is_limited
      });
      setHistory(data.history || []);
      setSignal(null);
    });
  }
  function loadAlerts(productId) {
    apiFetch(`/alerts/${productId}`).then(res => res.json()).then(data => setExistingAlerts(data.alerts || []));
  }
  function createAlert() {
    if (!selectedCard || !alertForm.threshold) return;
    apiFetch(`/create-alert/${selectedCard.id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        alert_type: alertForm.alert_type,
        threshold: parseFloat(alertForm.threshold) || 0
      })
    }).then(() => {
      setShowAlertModal(false);
      setAlertForm({
        alert_type: 'above',
        threshold: ''
      });
      loadAlerts(selectedCard.id);
    });
  }
  function deleteAlert(alertId) {
    if (!confirm('Delete this alert?')) return;
    apiFetch(`/delete-alert/${alertId}`, {
      method: 'DELETE'
    }).then(() => loadAlerts(selectedCard.id));
  }
  const rangeDays = {
    '7d': 7,
    '1m': 30,
    '3m': 90,
    '6m': 180,
    '1y': 365,
    'all': Infinity
  };
  const cutoffMs = Date.now() - rangeDays[chartRange] * 24 * 60 * 60 * 1000;
  const filteredHistory = chartRange === 'all' ? history : history.filter(h => new Date(h.recorded_at).getTime() >= cutoffMs);
  const trendingUp = filteredHistory.length >= 2 && filteredHistory[filteredHistory.length - 1].price > filteredHistory[0].price;
  const lineColor = trendingUp ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)';
  const fillColor = trendingUp ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)';
  const chartData = {
    labels: filteredHistory.map(h => new Date(h.recorded_at).toLocaleDateString()),
    datasets: [{
      label: 'Price',
      data: filteredHistory.map(h => h.price),
      borderColor: lineColor,
      backgroundColor: fillColor,
      fill: true,
      tension: 0.3,
      pointRadius: 4
    }]
  };
  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        display: false
      }
    },
    scales: {
      y: {
        ticks: {
          color: '#94a3b8'
        },
        grid: {
          color: '#334155'
        }
      },
      x: {
        ticks: {
          color: '#94a3b8'
        },
        grid: {
          color: '#334155'
        }
      }
    }
  };
  return <>
      <div className="relative mb-10">
        <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search for any Pokémon card..." className="w-full bg-slate-800 border border-slate-700 rounded-xl px-5 py-3 text-white placeholder-slate-400 focus:outline-none focus:border-red-500" />
        {query.length >= 2 && <div className="absolute top-full left-0 right-0 mt-2 bg-slate-800 border border-slate-700 rounded-xl max-h-96 overflow-y-auto z-10">
            {searching && <p className="p-4 text-slate-400">Searching...</p>}
            {!searching && searchResults.length === 0 && <p className="p-4 text-slate-400">No results found.</p>}
            {searchResults.map(card => <div key={card.poketrace_id} className="flex items-center gap-4 p-3 hover:bg-slate-700 cursor-pointer border-b border-slate-700" onClick={() => viewPublicCard(card.poketrace_id)}>
                <div className="flex-1">
                  <p className="font-semibold">{card.name}</p>
                  <p className="text-sm text-slate-400">
                    {card.set_name}
                    {card.number && ` · #${card.number}`}
                    {card.rarity && ` · ${card.rarity}`}
                  </p>
                </div>
                <div className="text-right">
                  {card.display_price && <p className="text-green-400 font-semibold text-sm">${card.display_price}</p>}
                  <button onClick={e => {
              e.stopPropagation();
              user ? saveCard(card.poketrace_id) : alert('Log in or create an account to save cards.');
            }} className="text-sm bg-red-500 hover:bg-red-600 px-3 py-1 rounded mt-1">Add</button>
                </div>
              </div>)}
          </div>}
      </div>

      {selectedCard && <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-10 grid grid-cols-1 md:grid-cols-[240px_1fr] gap-8">
          <div className="flex flex-col items-center md:items-start">
            <img src={selectedCard.image_url} alt={selectedCard.name} className="w-60 rounded-xl shadow-2xl" />
            <div className="mt-4 text-center md:text-left w-full">
              <h2 className="text-2xl font-bold">{selectedCard.name}</h2>
              <p className="text-slate-400 mb-3">{selectedCard.set_name}</p>
              <p className="text-4xl font-bold text-green-400">
                {condData?.price != null ? `$${condData.price}` : selectedCard.latest_price ? `$${selectedCard.latest_price}` : 'No price'}
              </p>
              <select value={condition} onChange={e => setCondition(e.target.value)} className="mt-3 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm w-full">
                <option value="NEAR_MINT">Near Mint</option>
                <option value="LIGHTLY_PLAYED">Lightly Played</option>
                <option value="MODERATELY_PLAYED">Moderately Played</option>
                <option value="HEAVILY_PLAYED">Heavily Played</option>
                <option value="DAMAGED">Damaged</option>
              </select>
              {signal && <div className="mt-4">
                  <span className={`inline-block px-4 py-2 rounded-lg font-bold text-lg ${signal.signal === 'BUY' ? 'bg-green-500 text-white' : signal.signal === 'SELL' ? 'bg-red-500 text-white' : signal.signal === 'HOLD' ? 'bg-yellow-500 text-black' : 'bg-slate-600 text-white'}`}>
                    {signal.signal}
                  </span>
                  <p className="text-sm text-slate-400 mt-2">{signal.reason}</p>
                  {signal.change_pct !== undefined && <p className={`text-sm mt-1 ${signal.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {signal.change_pct >= 0 ? '+' : ''}{signal.change_pct}% overall
                    </p>}
                </div>}
              <button onClick={() => user ? setShowAddModal(true) : alert('Log in or create an account to add cards to your collection.')} className="mt-6 w-full bg-red-500 hover:bg-red-600 text-white font-semibold py-3 rounded-lg transition-colors">
                + Add to Collection
              </button>
              <button onClick={() => user ? setShowAlertModal(true) : alert('Log in or create an account to set price alerts.')} className="mt-3 w-full bg-slate-700 hover:bg-slate-600 text-white font-semibold py-3 rounded-lg transition-colors">
                🔔 Set Price Alert
              </button>

              {existingAlerts.length > 0 && <div className="mt-4 text-left">
                  <p className="text-sm text-slate-400 mb-2">Active alerts:</p>
                  {existingAlerts.map(a => <div key={a.id} className="flex items-center justify-between bg-slate-900 rounded-lg px-3 py-2 mb-2">
                      <span className="text-sm">
                        {a.alert_type === 'above' ? '↗' : a.alert_type === 'below' ? '↘' : '%'} ${a.threshold}
                      </span>
                      <button onClick={() => deleteAlert(a.id)} className="text-red-400 hover:text-red-300 text-xs">
                        Remove
                      </button>
                    </div>)}
                </div>}
            </div>
          </div>
          <div className="flex flex-col justify-center">
            <StatsBar history={history} currentPrice={selectedCard.latest_price} />
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-300">Price History</h3>
              <div className="flex gap-1 bg-slate-900 rounded-lg p-1">
                {(user ? ['7d', '1m', '3m', '6m', '1y', 'all'] : ['7d', '1m']).map(range => <button key={range} onClick={() => setChartRange(range)} className={`px-3 py-1 text-xs font-semibold rounded transition-colors ${chartRange === range ? 'bg-red-500 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}>
                    {range.toUpperCase()}
                  </button>)}
              </div>
            </div>
            {filteredHistory.length >= 2 ? <Line data={chartData} options={chartOptions} /> : <p className="text-slate-400">
                {history.length < 2 ? 'Not enough price history yet. Needs at least 2 data points.' : `Not enough data in the ${chartRange.toUpperCase()} range. Try a longer period.`}
              </p>}
            {selectedCard.is_limited && <p className="text-sm text-amber-400 mt-3 text-center">
                Showing last 30 days. <a href="/signup" className="underline hover:text-amber-300">Create an account</a> to see full price history.
              </p>}
            {condData?.sales?.length > 0 && <div className="mt-6">
                <h3 className="text-lg font-semibold text-slate-300 mb-3">
                  Recent Sales — {condition.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}
                </h3>
                <div className="overflow-hidden rounded-lg border border-slate-700">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-900 text-slate-400">
                      <tr>
                        <th className="text-left p-2 px-3">Date</th>
                        <th className="text-left p-2 px-3">Sales</th>
                        <th className="text-right p-2 px-3">Price</th>
                        <th className="text-left p-2 px-3">Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {condData.sales.map((s, i) => <tr key={i} className="border-t border-slate-700">
                          <td className="p-2 px-3">{new Date(s.date).toLocaleDateString()}</td>
                          <td className="p-2 px-3">{s.sale_count}</td>
                          <td className="p-2 px-3 text-right">
                            {s.low === s.high ? `$${s.avg}` : `$${s.low}–$${s.high}`}
                          </td>
                          <td className="p-2 px-3 text-slate-400 capitalize">{s.source}</td>
                        </tr>)}
                    </tbody>
                  </table>
                </div>
              </div>}
          </div>
        </div>}
      {!user && <p className="text-slate-400 text-center py-20">
          Search any card above to see its price and history.<br />
          <a href="/signup" className="text-red-400 hover:text-red-300">Create an account</a> to save cards, track your collection, and log trades.
        </p>}

      {user && <h2 className="text-2xl font-semibold mb-6">Your Watchlist</h2>}

      {user && (loading ? <p className="text-slate-400">Loading...</p> : <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
            {(cards || []).map(card => <div key={card.id} onClick={() => selectCard(card)} className="group relative bg-slate-800 rounded-xl p-4 border border-slate-700 hover:border-red-500 transition-colors cursor-pointer">
                <button onClick={e => {
            e.stopPropagation();
            deleteCard(card.id);
          }} className="absolute top-2 right-2 bg-red-500 hover:bg-red-600 text-white w-7 h-7 rounded-full opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                  ×
                </button>
                <img src={card.image_url} alt={card.name} className="w-full rounded-lg mb-3" />
                <h3 className="font-semibold text-lg">{card.name}</h3>
                <p className="text-sm text-slate-400 mb-2">{card.set_name}</p>
                <p className="text-2xl font-bold text-green-400">
                  {card.latest_price ? `$${card.latest_price}` : 'No price'}
                </p>
              </div>)}
          </div>
          {cards.length === 0 && <p className="text-slate-400 text-center py-20">
              No cards saved yet. Use the search bar to add some.
            </p>}
        </>)}

      {showAddModal && <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setShowAddModal(false)}>
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h3 className="text-xl font-bold mb-4">Add to Collection</h3>
            <p className="text-slate-400 mb-6">{selectedCard?.name} - {selectedCard?.set_name}</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Quantity</label>
                <input type="number" min="1" value={addForm.quantity} onChange={e => setAddForm({
              ...addForm,
              quantity: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500" />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Price Paid (per card)</label>
                <input type="number" step="0.01" placeholder="0.00" value={addForm.price_paid} onChange={e => setAddForm({
              ...addForm,
              price_paid: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500" />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Priority</label>
                <select value={addForm.priority} onChange={e => setAddForm({
              ...addForm,
              priority: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500">
                 <option value="normal">Normal</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Condition</label>
                <select value={addForm.condition} onChange={e => setAddForm({
              ...addForm,
              condition: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500">
                  <option value="NEAR_MINT">Near Mint</option>
                  <option value="LIGHTLY_PLAYED">Lightly Played</option>
                  <option value="MODERATELY_PLAYED">Moderately Played</option>
                  <option value="HEAVILY_PLAYED">Heavily Played</option>
                  <option value="DAMAGED">Damaged</option>
                </select>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setShowAddModal(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg">
                Cancel
              </button>
              <button onClick={addToCollection} className="flex-1 bg-red-500 hover:bg-red-600 text-white font-semibold py-2 rounded-lg">
                Add
              </button>
            </div>
          </div>
        </div>}

      {showAlertModal && <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setShowAlertModal(false)}>
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h3 className="text-xl font-bold mb-4">Set Price Alert</h3>
            <p className="text-slate-400 mb-6">{selectedCard?.name} - {selectedCard?.set_name}</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Alert when price goes</label>
                <select value={alertForm.alert_type} onChange={e => setAlertForm({
              ...alertForm,
              alert_type: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500">
                  <option value="above">Above (price rises to)</option>
                  <option value="below">Below (price drops to)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Threshold ($)</label>
                <input type="number" step="0.01" placeholder="400.00" value={alertForm.threshold} onChange={e => setAlertForm({
              ...alertForm,
              threshold: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500" />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setShowAlertModal(false)} className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg">
                Cancel
              </button>
              <button onClick={createAlert} className="flex-1 bg-red-500 hover:bg-red-600 text-white font-semibold py-2 rounded-lg">
                Create Alert
              </button>
            </div>
          </div>
        </div>}
    </>;
}
export default Market;
