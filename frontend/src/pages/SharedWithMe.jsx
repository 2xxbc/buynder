import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../config';
function timeLeft(expiresAt) {
  if (!expiresAt) return 'No expiry';
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return 'Expired';
  const hrs = Math.floor(ms / 3600000);
  const mins = Math.floor(ms % 3600000 / 60000);
  return `${hrs}h ${mins}m left`;
}
function MyShareRow({
  share
}) {
  const [open, setOpen] = useState(false);
  const [viewers, setViewers] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && viewers === null) {
      setLoading(true);
      apiFetch(`/share-viewers/${share.id}`).then(res => res.json()).then(d => {
        setViewers(d);
        setLoading(false);
      }).catch(() => setLoading(false));
    }
  }
  function copyLink() {
    navigator.clipboard.writeText(`${window.location.origin}/shared/${share.token}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="flex items-center gap-3 p-4">
        <div className="flex-1 min-w-0">
          <p className="font-medium truncate">{share.label || 'Untitled link'}</p>
          <p className="text-xs text-amber-400">{timeLeft(share.expires_at)}</p>
        </div>
        <button onClick={copyLink} className="text-xs bg-slate-700 hover:bg-slate-600 px-3 py-1.5 rounded transition-colors">
          {copied ? 'Copied!' : 'Copy link'}
        </button>
        <button onClick={toggle} className="text-xs text-slate-400 hover:text-white px-2 py-1.5 flex items-center gap-1">
          Who has access
          <span className={`transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
        </button>
      </div>

      {open && <div className="border-t border-slate-700 bg-slate-900/50 px-4 py-3">
          {loading ? <p className="text-xs text-slate-500">Loading…</p> : !viewers || viewers.total === 0 ? <p className="text-xs text-slate-500">Nobody has opened this link yet.</p> : <>
              <div className="space-y-2">
                {viewers.viewers.map((v, i) => <div key={i} className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
                      {v.username.charAt(0).toUpperCase()}
                    </div>
                    <span className="text-sm">{v.username}</span>
                    <span className="text-xs text-slate-500 ml-auto">
                      {new Date(v.first_opened).toLocaleDateString()}
                    </span>
                  </div>)}
              </div>
              {viewers.total > 10 && <p className="text-xs text-slate-500 mt-3">
                  Showing 10 of {viewers.total} people with access.
                </p>}
            </>}
        </div>}
    </div>;
}
function SharedWithMe() {
  const [shares, setShares] = useState([]);
  const [myShares, setMyShares] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    Promise.all([apiFetch('/shared-with-me').then(r => r.json()).catch(() => ({})), apiFetch('/my-shares').then(r => r.json()).catch(() => ({}))]).then(([incoming, outgoing]) => {
      setShares(incoming.shares || []);
      setMyShares((outgoing.shares || []).filter(s => s.active));
      setLoading(false);
    });
  }, []);
  if (loading) return <p className="text-slate-400 text-center py-24">Loading…</p>;
  return <>
      <h2 className="text-3xl font-bold mb-2">Shared</h2>
      <p className="text-slate-400 mb-10">Collections shared with you, and links you've sent out.</p>

      
      <h3 className="text-xl font-semibold mb-4">Shared with me</h3>
      {shares.length === 0 ? <div className="bg-slate-800 border border-slate-700 rounded-xl p-8 text-center mb-12">
          <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-xl">
            👋
          </div>
          <p className="font-semibold mb-1">Nothing shared yet</p>
          <p className="text-sm text-slate-400">
            Ask a friend to share their collection. Once you open their link, it'll show up here.
          </p>
        </div> : <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
          {shares.map(s => <Link key={s.token} to={`/shared/${s.token}`} className="bg-slate-800 rounded-xl border border-slate-700 hover:border-amber-500 p-5 transition-colors">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center font-bold text-white">
                  {s.owner_name.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="font-semibold truncate">{s.owner_name}</p>
                  {s.label && <p className="text-xs text-slate-500 truncate">{s.label}</p>}
                </div>
              </div>
              <p className="text-sm text-amber-400">{timeLeft(s.expires_at)}</p>
              <p className="text-xs text-slate-500 mt-2">Click to view their collection & trades</p>
            </Link>)}
        </div>}

      
      <h3 className="text-xl font-semibold mb-4">My shared links</h3>
      {myShares.length === 0 ? <p className="text-sm text-slate-500">
          You haven't shared anything yet. Head to your Collection and hit Share to create a link.
        </p> : <div className="space-y-3">
          {myShares.map(s => <MyShareRow key={s.id} share={s} />)}
        </div>}
    </>;
}
export default SharedWithMe;
