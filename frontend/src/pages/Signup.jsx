import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import AuthShell from '../components/AuthShell'
import { btn, field, label } from '../components/ui'

function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [website, setWebsite] = useState('') // honeypot: stays empty for people
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e?.preventDefault()
    setError('')
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setBusy(true)
    const result = await signup(username, email, password, website)
    setBusy(false)
    if (result.success) {
      navigate('/')
    } else {
      setError(result.error)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Free. Track prices, your collection and trades."
      error={error}
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-chalk underline underline-offset-4">Log in</Link></>}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Honeypot for bots: off-screen, skipped by Tab, hidden from screen readers. A person never
            fills it in; a bot that fills every field gets turned away by the server. */}
        <div aria-hidden="true" className="absolute -left-[10000px] top-auto w-px h-px overflow-hidden">
          <label htmlFor="signup-website">Website</label>
          <input id="signup-website" type="text" name="website" tabIndex={-1} autoComplete="off"
            value={website} onChange={e => setWebsite(e.target.value)} />
        </div>
        <div>
          <label htmlFor="signup-username" className={label}>Username</label>
          <input id="signup-username" className={field} type="text" autoComplete="username"
            maxLength={30} value={username} onChange={e => setUsername(e.target.value)} placeholder="Choose a username" />
        </div>
        <div>
          <label htmlFor="signup-email" className={label}>Email</label>
          <input id="signup-email" className={field} type="email" autoComplete="email"
            value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>
        <div>
          <label htmlFor="signup-password" className={label}>Password</label>
          <input id="signup-password" className={field} type="password" autoComplete="new-password"
            aria-describedby="signup-password-hint"
            maxLength={72} value={password} onChange={e => setPassword(e.target.value)} placeholder="Create a password" />
          <p id="signup-password-hint" className="text-xs text-chalk-soft mt-1.5">8 to 72 characters</p>
        </div>
        <button type="submit" disabled={busy} className={`${btn.primary} w-full mt-2`}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  )
}

export default Signup
