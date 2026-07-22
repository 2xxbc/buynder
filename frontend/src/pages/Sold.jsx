import { useState, useEffect } from 'react';
import { API_URL, apiFetch } from '../config';
function Sold() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({
    total_sold: 0,
    count: 0
  });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    loadSold();
  }, []);
  function loadSold() {
    apiFetch('/sold').then(res => res.json()).then(data => {
      setItems(data.items || []);
      setStats(data.stats || {});
      setLoading(false);
    });
  }
  return <>
      <h2 className="text-3xl font-bold mb-8">Sold History</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10">
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <p className="text-sm text-slate-400">Total Sales</p>
          <p className="text-3xl font-bold text-green-400">${stats.total_sold}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <p className="text-sm text-slate-400">Cards Sold</p>
          <p className="text-3xl font-bold">{stats.count}</p>
        </div>
      </div>

      {loading ? <p className="text-slate-400">Loading...</p> : items.length === 0 ? <p className="text-slate-400 text-center py-20">No sales yet. Mark a card as sold from your Collection page.</p> : <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-900">
              <tr className="text-left text-sm text-slate-400">
                <th className="p-4">Card</th>
                <th className="p-4">Sold Price</th>
                <th className="p-4">Platform</th>
                <th className="p-4">Date</th>
                <th className="p-4">Notes</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => <tr key={item.sold_id} className="border-t border-slate-700">
                  <td className="p-4 flex items-center gap-3">
                    <img src={item.image_url} alt={item.name} className="w-12 rounded" />
                    <div>
                      <p className="font-semibold">{item.name}</p>
                      <p className="text-sm text-slate-400">{item.set_name}</p>
                    </div>
                  </td>
                  <td className="p-4 text-green-400 font-semibold">${item.sale_price}</td>
                  <td className="p-4">{item.platform || '-'}</td>
                  <td className="p-4 text-slate-400 text-sm">{new Date(item.sold_at).toLocaleDateString()}</td>
                  <td className="p-4 text-slate-400 text-sm">{item.notes || '-'}</td>
                </tr>)}
            </tbody>
          </table>
        </div>}
    </>;
}
export default Sold;
