import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import AuthShell from '../components/AuthShell'
import { btn, field, label } from '../components/ui'

function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e?.preventDefault()
    setError('')
    setBusy(true)
    const result = await login(username, password)
    setBusy(false)
    if (result.success) {
      navigate('/')
    } else {
      setError(result.error)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Log in to track your collection."
      error={error}
      footer={<>New here? <Link to="/signup" className="font-semibold text-chalk underline underline-offset-4">Create an account</Link></>}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="login-username" className={label}>Username</label>
          <input id="login-username" className={field} type="text" autoComplete="username"
            value={username} onChange={e => setUsername(e.target.value)} placeholder="Your username" />
        </div>
        <div>
          <label htmlFor="login-password" className={label}>Password</label>
          <input id="login-password" className={field} type="password" autoComplete="current-password"
            value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" />
        </div>
        <button type="submit" disabled={busy} className={`${btn.primary} w-full mt-2`}>
          {busy ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </AuthShell>
  )
}

export default Login
