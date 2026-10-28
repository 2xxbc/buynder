import { createContext, useContext, useState, useEffect } from 'react'
import { API_URL } from './config'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // Check if already logged in when the app loads
  useEffect(() => {
    fetch(`${API_URL}/me`, { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setUser(data.user || null)
        setLoading(false)
      })
      .catch(() => {
        setUser(null)
        setLoading(false)
      })
  }, [])

  function login(username, password) {
    return fetch(`${API_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
      .then(res => res.json().then(data => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success) {
          setUser(data.user)
          return { success: true }
        }
        return { success: false, error: data.error || 'Login failed' }
      })
  }

  function signup(username, email, password, website = '') {
    return fetch(`${API_URL}/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, email, password, website }),
    })
      .then(res => res.json().then(data => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success) {
          setUser(data.user)
          return { success: true }
        }
        return { success: false, error: data.error || 'Signup failed' }
      })
  }

  function logout() {
    return fetch(`${API_URL}/logout`, {
      method: 'POST',
      credentials: 'include',
    }).then(() => setUser(null))
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

// Hook lives next to its provider on purpose
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext)
}
