import { useState, useEffect } from 'react';
import { apiFetch } from '../config';
function ShareManager() {
  const [open, setOpen] = useState(false);
  const [shares, setShares] = useState([]);
  const [duration, setDuration] = useState('24h');
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState('');
  useEffect(() => {
    if (open) loadShares();
  }, [open]);
  function loadShares() {
    apiFetch('/my-shares').then(res => res.json()).then(data => setShares(data.shares || [])).catch(() => {});
  }
  function createShare() {
    setCreating(true);
    apiFetch('/create-share', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        duration,
        label
      })
    }).then(res => res.json()).then(data => {
      setCreating(false);
      if (data.success) {
        setLabel('');
        loadShares();
      } else {
        alert(data.error || 'Failed to create link');
      }
    }).catch(() => setCreating(false));
  }
  function revokeShare(id) {
    if (!confirm('Turn off this share link? The person will lose access.')) return;
    apiFetch(`/revoke-share/${id}`, {
      method: 'POST'
    }).then(() => loadShares());
  }
  function shareUrl(token) {
    return `${window.location.origin}/shared/${token}`;
  }
  function copyLink(token) {
    navigator.clipboard.writeText(shareUrl(token));
    setCopied(token);
    setTimeout(() => setCopied(''), 2000);
  }
  function timeLeft(expiresAt) {
    if (!expiresAt) return 'No expiry';
    const ms = new Date(expiresAt).getTime() - Date.now();
    if (ms <= 0) return 'Expired';
    const hrs = Math.floor(ms / 3600000);
    const mins = Math.floor(ms % 3600000 / 60000);
    return `${hrs}h ${mins}m left`;
  }
  return <>
      <button onClick={() => setOpen(true)} className="bg-gradient-to-r from-amber-500 to-orange-600 hover:opacity-90 text-white font-semibold px-4 py-2 rounded-lg transition-opacity">
        Share
      </button>

      {open && <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setOpen(false)}>
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold">Share your collection & trades</h3>
              <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <p className="text-sm text-slate-400 mb-4">
              Create a view-only link. Anyone you send it to (who's logged in) can see your collection and trades until it expires.
            </p>

            
            <div className="bg-slate-900 rounded-lg p-4 mb-5">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Viewable for</label>
                  <select value={duration} onChange={e => setDuration(e.target.value)} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm">
                    <option value="1h">1 hour</option>
                    <option value="12h">12 hours</option>
                    <option value="24h">24 hours</option>
                    <option value="infinite">No expiry (until I turn it off)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Label (optional)</label>
                  <input type="text" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. for Jake" className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm" />
                </div>
              </div>
              <button onClick={createShare} disabled={creating} className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-semibold py-2 rounded-lg transition-colors">
                {creating ? 'Creating…' : 'Create link'}
              </button>
            </div>

            
            <div>
              <p className="text-sm font-semibold text-slate-300 mb-2">Your active links</p>
              {shares.filter(s => s.active).length === 0 && <p className="text-sm text-slate-500">No active links yet.</p>}
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {shares.filter(s => s.active).map(s => <div key={s.id} className="bg-slate-900 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">{s.label || 'Untitled link'}</span>
                      <span className="text-xs text-slate-400">{timeLeft(s.expires_at)}</span>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => copyLink(s.token)} className="flex-1 text-xs bg-slate-700 hover:bg-slate-600 text-white py-1.5 rounded transition-colors">
                        {copied === s.token ? 'Copied!' : 'Copy link'}
                      </button>
                      <button onClick={() => revokeShare(s.id)} className="text-xs bg-red-500/20 hover:bg-red-500/40 text-red-300 px-3 py-1.5 rounded transition-colors">
                        Turn off
                      </button>
                    </div>
                  </div>)}
              </div>
            </div>
          </div>
        </div>}
    </>;
}
export default ShareManager;
