import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../config';
import { useAuth } from '../AuthContext';
import { Link } from 'react-router-dom';
function SharedView() {
  const {
    token
  } = useParams();
  const {
    user,
    loading: authLoading
  } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [timeLeft, setTimeLeft] = useState('');
  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setLoading(false);
      return;
    }
    apiFetch(`/shared/${token}`).then(res => res.json().then(d => ({
      ok: res.ok,
      d
    }))).then(({
      ok,
      d
    }) => {
      if (ok) setData(d);else setError(d.error || 'Could not load this link.');
      setLoading(false);
    }).catch(() => {
      setError('Something went wrong.');
      setLoading(false);
    });
  }, [token, user, authLoading]);
  useEffect(() => {
    if (!data?.expires_at) {
      setTimeLeft(data ? 'No expiry' : '');
      return;
    }
    const tick = () => {
      const ms = new Date(data.expires_at).getTime() - Date.now();
      if (ms <= 0) {
        setTimeLeft('Expired');
        setError('This share link has expired.');
        return;
      }
      const hrs = Math.floor(ms / 3600000);
      const mins = Math.floor(ms % 3600000 / 60000);
      const secs = Math.floor(ms % 60000 / 1000);
      setTimeLeft(`${hrs}h ${mins}m ${secs}s left`);
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [data]);
  const fmtMoney = v => v === null || v === undefined ? '—' : `$${v}`;
  if (authLoading || loading) {
    return <p className="text-slate-400 text-center py-24">Loading…</p>;
  }
  if (!user) {
    return <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-10 max-w-md">
          <h2 className="text-2xl font-bold mb-2">Log in to view this</h2>
          <p className="text-slate-400 mb-6">Someone shared their collection with you. Log in or create an account to see it.</p>
          <div className="flex gap-3 justify-center">
            <Link to="/login" className="px-5 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white font-semibold">Log in</Link>
            <Link to="/signup" className="px-5 py-2 rounded-lg bg-gradient-to-r from-amber-500 to-orange-600 text-white font-semibold">Create account</Link>
          </div>
        </div>
      </div>;
  }
  if (error) {
    return <div className="text-center py-24">
        <p className="text-xl font-semibold mb-2">{error}</p>
        <Link to="/" className="text-amber-400 hover:text-amber-300">Back to BuynderMarket</Link>
      </div>;
  }
  if (!data) return null;
  return <>
      <div className="flex items-center justify-between mb-8 flex-wrap gap-3">
        <div>
          <h2 className="text-3xl font-bold">{data.owner_name}'s Collection</h2>
          <p className="text-slate-400 text-sm">View-only shared link</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-sm">
          <span className="text-slate-400">Access: </span>
          <span className="text-amber-400 font-semibold">{timeLeft}</span>
        </div>
      </div>

      
      <h3 className="text-xl font-semibold mb-4">Collection ({data.collection.length})</h3>
      {data.collection.length === 0 ? <p className="text-slate-400 mb-10">No cards in their collection.</p> : <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-12">
          {data.collection.map((c, i) => <div key={i} className="bg-slate-800 rounded-xl p-4 border border-slate-700">
              <img src={c.image_url} alt={c.name} className="w-full rounded-lg mb-3" />
              <h4 className="font-semibold">{c.name}</h4>
              <p className="text-sm text-slate-400 mb-2">{c.set_name}</p>
              <p className="text-xl font-bold text-green-400">{fmtMoney(c.current_price)}</p>
              <p className="text-xs text-slate-500 mt-1">Qty: {c.quantity} · Paid {fmtMoney(c.price_paid)}</p>
            </div>)}
        </div>}

      
      <h3 className="text-xl font-semibold mb-4">Trades ({data.trades.length})</h3>
      {data.trades.length === 0 ? <p className="text-slate-400">No trades logged.</p> : <div className="space-y-3">
          {data.trades.map(t => <div key={t.id} className="bg-slate-800 rounded-xl border border-slate-700 p-4">
              <p className="text-xs text-slate-500 mb-2">{new Date(t.trade_date).toLocaleDateString()}</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">Gave</p>
                  {t.gave_cards.map((c, i) => <p key={i} className="text-sm">{c.name} <span className="text-slate-500">({fmtMoney(c.agreed)})</span></p>)}
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">Got</p>
                  {t.got_cards.map((c, i) => <p key={i} className="text-sm">{c.name} <span className="text-slate-500">({fmtMoney(c.agreed)})</span></p>)}
                </div>
              </div>
              {t.cash_direction !== 'none' && <p className="text-sm text-slate-400 mt-2">Cash: {t.cash_direction === 'paid' ? 'paid' : 'received'} ${t.cash_amount}</p>}
              {t.notes && <p className="text-sm text-slate-500 mt-1 italic">{t.notes}</p>}
            </div>)}
        </div>}
    </>;
}
export default SharedView;
