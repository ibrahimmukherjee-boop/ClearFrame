import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export interface AuthUser {
  userId: string
  email: string
  name: string
  role: 'admin' | 'operator' | 'auditor'
}

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithSso: () => Promise<void>
  logout: () => void
  isAuthenticated: boolean
  ssoAvailable: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)
const TOKEN_KEY = 'erasys_access_token'
const USER_KEY = 'erasys_user'

function parseSsoHash(): { accessToken: string; user: AuthUser } | null {
  const hash = window.location.hash.slice(1)
  if (!hash.includes('accessToken=')) return null
  const params = new URLSearchParams(hash)
  const accessToken = params.get('accessToken')
  const userRaw = params.get('user')
  if (!accessToken || !userRaw) return null
  try {
    return { accessToken, user: JSON.parse(decodeURIComponent(userRaw)) as AuthUser }
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [ssoAvailable, setSsoAvailable] = useState(false)

  useEffect(() => {
    const sso = parseSsoHash()
    if (sso) {
      localStorage.setItem(TOKEN_KEY, sso.accessToken)
      localStorage.setItem(USER_KEY, JSON.stringify(sso.user))
      setToken(sso.accessToken)
      setUser(sso.user)
      window.history.replaceState(null, '', window.location.pathname)
      setLoading(false)
      return
    }
    const stored = localStorage.getItem(TOKEN_KEY)
    const storedUser = localStorage.getItem(USER_KEY)
    if (stored && storedUser) {
      setToken(stored)
      setUser(JSON.parse(storedUser))
    }
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setSsoAvailable(!!d.ssoEnabled))
      .catch(() => {})
    setLoading(false)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    localStorage.setItem(TOKEN_KEY, data.accessToken)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    setToken(data.accessToken)
    setUser(data.user)
  }, [])

  const loginWithSso = useCallback(async () => {
    const res = await fetch('/api/auth/oidc/login')
    if (!res.ok) throw new Error('SSO not configured')
    const data = await res.json()
    window.location.href = data.url
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, loading, login, loginWithSso, logout, isAuthenticated: !!token, ssoAvailable }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
