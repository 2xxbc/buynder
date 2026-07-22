import { useState, useEffect } from 'react';
import { API_URL, apiFetch } from '../config';
import ShareManager from '../components/ShareManager';
const CONDITIONS = {
  NEAR_MINT: {
    label: 'NM',
    color: 'bg-green-600'
  },
  LIGHTLY_PLAYED: {
    label: 'LP',
    color: 'bg-lime-600'
  },
  MODERATELY_PLAYED: {
    label: 'MP',
    color: 'bg-yellow-600'
  },
  HEAVILY_PLAYED: {
    label: 'HP',
    color: 'bg-orange-600'
  },
  DAMAGED: {
    label: 'DMG',
    color: 'bg-red-600'
  }
};
const condLabel = c => CONDITIONS[c]?.label || 'NM';
const condColor = c => CONDITIONS[c]?.color || 'bg-slate-600';
function Collection() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({
    total_paid: 0,
    total_value: 0,
    unrealized_pnl: 0
  });
  const [loading, setLoading] = useState(true);
  const [sellingItem, setSellingItem] = useState(null);
  const [sellForm, setSellForm] = useState({
    sale_price: '',
    platform: '',
    notes: ''
  });
  useEffect(() => {
    loadCollection();
  }, []);
  function loadCollection() {
    apiFetch('/collection').then(res => res.json()).then(data => {
      setItems(data.items || []);
      setStats(data.stats || {});
      setLoading(false);
    });
  }
  function removeItem(collectionId) {
    if (!confirm('Remove this from your collection?')) return;
    apiFetch(`/remove-from-collection/${collectionId}`, {
      method: 'DELETE'
    }).then(() => loadCollection());
  }
  function markSold() {
    if (!sellingItem) return;
    apiFetch(`/mark-sold/${sellingItem.collection_id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        sale_price: parseFloat(sellForm.sale_price) || 0,
        platform: sellForm.platform,
        notes: sellForm.notes
      })
    }).then(() => {
      setSellingItem(null);
      setSellForm({
        sale_price: '',
        platform: '',
        notes: ''
      });
      loadCollection();
    });
  }
  return <>
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-3xl font-bold">My Collection</h2>
        <ShareManager />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <p className="text-sm text-slate-400">Binder Worth</p>
          <p className="text-3xl font-bold text-green-400">${stats.total_value}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <p className="text-sm text-slate-400">Total Paid</p>
          <p className="text-3xl font-bold">${stats.total_paid}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <p className="text-sm text-slate-400">Unrealized P&L</p>
          <p className={`text-3xl font-bold ${stats.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {stats.unrealized_pnl >= 0 ? '+' : ''}${stats.unrealized_pnl}
          </p>
        </div>
      </div>

      {loading ? <p className="text-slate-400">Loading...</p> : items.length === 0 ? <p className="text-slate-400 text-center py-20">No cards in your collection yet.</p> : <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-900">
              <tr className="text-left text-sm text-slate-400">
                <th className="p-4">Card</th>
                <th className="p-4">Qty</th>
                <th className="p-4">Current</th>
                <th className="p-4">Condition</th>
                <th className="p-4">P&L</th>
                <th className="p-4">Priority</th>
                <th className="p-4"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => <tr key={item.collection_id} className="border-t border-slate-700">
                  <td className="p-4 flex items-center gap-3">
                    <img src={item.image_url} alt={item.name} className="w-12 rounded" />
                    <div>
                      <p className="font-semibold">{item.name}</p>
                      <p className="text-sm text-slate-400">{item.set_name}</p>
                    </div>
                  </td>
                  <td className="p-4">{item.quantity}</td>
                  <td className="p-4">${item.price_paid}</td>
                  <td className="p-4">${item.current_price || '0.00'}</td>
                  <td className="p-4">
                    <span className={`text-xs px-2 py-1 rounded text-white ${condColor(item.card_condition)}`}>
                      {condLabel(item.card_condition)}
                    </span>
                  </td>
                  <td className={`p-4 font-semibold ${item.profit_loss >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {item.profit_loss >= 0 ? '+' : ''}${item.profit_loss.toFixed(2)}
                  </td>
                  <td className="p-4">
                    <span className={`text-xs px-2 py-1 rounded ${item.priority === 'high' ? 'bg-red-500' : 'bg-slate-600'}`}>
                      {item.priority}
                    </span>
                  </td>
                  <td className="p-4 flex gap-2">
                    <button onClick={() => setSellingItem(item)} className="text-xs bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded">
                      Sell
                    </button>
                    <button onClick={() => removeItem(item.collection_id)} className="text-red-400 hover:text-red-300 text-sm">
                      Remove
                    </button>
                  </td>
                </tr>)}
            </tbody>
          </table>
        </div>}

      {sellingItem && <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setSellingItem(null)}>
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h3 className="text-xl font-bold mb-4">Mark as Sold</h3>
            <p className="text-slate-400 mb-6">{sellingItem.name} - {sellingItem.set_name}</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Sale Price</label>
                <input type="number" step="0.01" placeholder="0.00" value={sellForm.sale_price} onChange={e => setSellForm({
              ...sellForm,
              sale_price: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500" />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Platform</label>
                <input type="text" placeholder="eBay, TCGPlayer, Local, etc." value={sellForm.platform} onChange={e => setSellForm({
              ...sellForm,
              platform: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500" />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Notes (optional)</label>
                <textarea rows="3" placeholder="Any notes about this sale..." value={sellForm.notes} onChange={e => setSellForm({
              ...sellForm,
              notes: e.target.value
            })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-red-500" />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setSellingItem(null)} className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg">
                Cancel
              </button>
              <button onClick={markSold} className="flex-1 bg-green-500 hover:bg-green-600 text-white font-semibold py-2 rounded-lg">
                Confirm Sale
              </button>
            </div>
          </div>
        </div>}
    </>;
}
export default Collection;
