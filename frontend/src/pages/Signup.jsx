import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';
function Signup() {
  const {
    signup
  } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function handleSubmit() {
    setError('');
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setBusy(true);
    const result = await signup(username, email, password, code);
    setBusy(false);
    if (result.success) {
      navigate('/');
    } else {
      setError(result.error);
    }
  }
  return <div className="login-root">
      <style>{`
        .login-root {
          min-height: 100vh; display: flex; align-items: center; justify-content: center;
          padding: 1.5rem;
          background:
            radial-gradient(1200px 600px at 15% -10%, rgba(245, 158, 11, 0.10), transparent 60%),
            radial-gradient(1000px 500px at 110% 110%, rgba(239, 68, 68, 0.08), transparent 55%),
            linear-gradient(180deg, #0a0e1a 0%, #0d1322 100%);
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        }
        .login-card {
          width: 100%; max-width: 400px;
          background: linear-gradient(180deg, rgba(23, 31, 50, 0.9) 0%, rgba(17, 24, 40, 0.9) 100%);
          border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 20px;
          padding: 2.5rem 2.25rem;
          box-shadow: 0 1px 0 0 rgba(255, 255, 255, 0.04) inset, 0 20px 50px -20px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(0, 0, 0, 0.2);
          backdrop-filter: blur(12px);
        }
        .login-brand { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 2rem; }
        .login-orb {
          width: 30px; height: 30px; border-radius: 50%;
          background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
          box-shadow: 0 0 20px -2px rgba(245, 158, 11, 0.6); position: relative; flex-shrink: 0;
        }
        .login-orb::after {
          content: ''; position: absolute; inset: 0; border-radius: 50%;
          background: radial-gradient(circle at 32% 30%, rgba(255,255,255,0.7), transparent 40%);
        }
        .login-wordmark { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; color: #f1f5f9; }
        .login-wordmark span { color: #f59e0b; }
        .login-heading { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.025em; color: #f8fafc; margin: 0 0 0.4rem 0; line-height: 1.15; }
        .login-sub { font-size: 0.9rem; color: #94a3b8; margin: 0 0 1.75rem 0; }
        .login-error {
          background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3);
          color: #fca5a5; border-radius: 10px; padding: 0.7rem 0.85rem; margin-bottom: 1.1rem; font-size: 0.85rem;
        }
        .login-field { margin-bottom: 1.1rem; }
        .login-label { display: block; font-size: 0.78rem; font-weight: 500; color: #94a3b8; margin-bottom: 0.45rem; letter-spacing: 0.01em; }
        .login-input {
          width: 100%; box-sizing: border-box; background: rgba(10, 14, 26, 0.6);
          border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 11px; padding: 0.7rem 0.85rem;
          color: #f1f5f9; font-size: 0.95rem; transition: border-color 0.15s, box-shadow 0.15s, background 0.15s; outline: none;
        }
        .login-input::placeholder { color: #475569; }
        .login-input:focus {
          border-color: rgba(245, 158, 11, 0.5); background: rgba(10, 14, 26, 0.85);
          box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.12);
        }
        .login-hint { font-size: 0.72rem; color: #64748b; margin-top: 0.35rem; }
        .login-btn {
          width: 100%; margin-top: 0.4rem;
          background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%);
          color: #1a1206; font-weight: 650; font-size: 0.95rem; border: none; border-radius: 11px; padding: 0.8rem;
          cursor: pointer; letter-spacing: 0.01em; box-shadow: 0 8px 20px -8px rgba(245, 158, 11, 0.6);
          transition: transform 0.1s, box-shadow 0.2s, opacity 0.2s;
        }
        .login-btn:hover:not(:disabled) { box-shadow: 0 10px 26px -8px rgba(245, 158, 11, 0.75); transform: translateY(-1px); }
        .login-btn:active:not(:disabled) { transform: translateY(0); }
        .login-btn:disabled { opacity: 0.6; cursor: default; }
        .login-foot { font-size: 0.85rem; color: #94a3b8; margin: 1.6rem 0 0 0; text-align: center; }
        .login-foot a { color: #f59e0b; text-decoration: none; font-weight: 500; }
        .login-foot a:hover { color: #fbbf24; }
      `}</style>

      <div className="login-card">
        <div className="login-brand">
          <img src="/icon_buynder4.png" alt="Buynder" className="h-32 w-auto mb-4" />
        </div>

        <h1 className="login-heading">Create your account</h1>
        <p className="login-sub">Enter your invite code to get started.</p>

        {error && <div className="login-error">{error}</div>}

        <div className="login-field">
          <label className="login-label">Invite Code</label>
          <input className="login-input" type="text" value={code} onChange={e => setCode(e.target.value)} placeholder="POKEBALL-XXXX" />
        </div>

        <div className="login-field">
          <label className="login-label">Username</label>
          <input className="login-input" type="text" value={username} onChange={e => setUsername(e.target.value)} placeholder="Choose a username" />
        </div>

        <div className="login-field">
          <label className="login-label">Email</label>
          <input className="login-input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>

        <div className="login-field">
          <label className="login-label">Password</label>
          <input className="login-input" type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()} placeholder="Create a password" />
          <p className="login-hint">At least 8 characters</p>
        </div>

        <button className="login-btn" onClick={handleSubmit} disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>

        <p className="login-foot">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>;
}
export default Signup;
