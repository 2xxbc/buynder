import { useState, useEffect } from 'react';
import { API_URL, apiFetch } from '../config';
function Portfolio() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiFetch('/portfolio').then(res => res.json()).then(d => {
      setData(d);
      setLoading(false);
    });
  }, []);
  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (!data) return <p className="text-slate-400">No data.</p>;
  const StatCard = ({
    label,
    value,
    color = 'white'
  }) => <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
      <p className="text-sm text-slate-400 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color === 'green' ? 'text-green-400' : color === 'red' ? 'text-red-400' : 'text-white'}`}>
        {value}
      </p>
    </div>;
  return <>
      <h2 className="text-3xl font-bold mb-8">Portfolio Dashboard</h2>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
        <StatCard label="Binder Worth" value={`$${data.binder_worth}`} color="green" />
        <StatCard label="Total Paid" value={`$${data.total_paid}`} />
        <StatCard label="Unrealized P&L" value={`${data.unrealized_pnl >= 0 ? '+' : ''}$${data.unrealized_pnl}`} color={data.unrealized_pnl >= 0 ? 'green' : 'red'} />
        <StatCard label="Total Sold" value={`$${data.total_sold}`} color="green" />
        <StatCard label="Realized P&L" value={`${data.realized_pnl >= 0 ? '+' : ''}$${data.realized_pnl}`} color={data.realized_pnl >= 0 ? 'green' : 'red'} />
        <StatCard label="Total P&L" value={`${data.total_pnl >= 0 ? '+' : ''}$${data.total_pnl}`} color={data.total_pnl >= 0 ? 'green' : 'red'} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {data.biggest_gainer && <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
            <h3 className="text-lg font-semibold mb-4 text-green-400">Biggest Gainer</h3>
            <div className="flex items-center gap-4">
              <img src={data.biggest_gainer.image_url} alt={data.biggest_gainer.name} className="w-20 rounded-lg" />
              <div>
                <p className="font-semibold text-lg">{data.biggest_gainer.name}</p>
                <p className="text-sm text-slate-400">{data.biggest_gainer.set_name}</p>
                <p className="text-2xl font-bold text-green-400 mt-1">+{data.biggest_gainer.change_pct}%</p>
              </div>
            </div>
          </div>}

        {data.biggest_loser && <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
            <h3 className="text-lg font-semibold mb-4 text-red-400">Biggest Loser</h3>
            <div className="flex items-center gap-4">
              <img src={data.biggest_loser.image_url} alt={data.biggest_loser.name} className="w-20 rounded-lg" />
              <div>
                <p className="font-semibold text-lg">{data.biggest_loser.name}</p>
                <p className="text-sm text-slate-400">{data.biggest_loser.set_name}</p>
                <p className="text-2xl font-bold text-red-400 mt-1">{data.biggest_loser.change_pct}%</p>
              </div>
            </div>
          </div>}
      </div>
    </>;
}
export default Portfolio;
