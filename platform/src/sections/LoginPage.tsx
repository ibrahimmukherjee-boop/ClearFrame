import { useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Shield, LogIn, AlertCircle, Server } from 'lucide-react'
import { useAuth } from '@/lib/auth-store'
import { apiUrl, getBackend, setBackend } from '@/lib/api'
import { toast } from 'sonner'

const DEMO_EMAIL = 'admin@erasys.local'
const DEMO_PASSWORD = 'Clearframe2026'

export function LoginPage() {
  const { login, loginWithSso, ssoAvailable } = useAuth()
  const [email, setEmail] = useState(DEMO_EMAIL)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isProduction, setIsProduction] = useState(false)
  const [backend, setBackendUrl] = useState(getBackend())
  const [reachable, setReachable] = useState<boolean | null>(null)

  useEffect(() => {
    fetch(apiUrl('/health'))
      .then((r) => r.json())
      .then((d) => { setIsProduction(Boolean(d.production?.production)); setReachable(true) })
      .catch(() => setReachable(false))
  }, [])

  const saveBackend = () => {
    setBackend(backend)
    toast.success(backend ? `Backend set to ${backend}` : 'Using same-origin backend')
    setTimeout(() => window.location.reload(), 400)
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email.trim(), password)
      toast.success('Signed in successfully')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Login failed'
      setError(msg === 'Invalid credentials'
        ? 'Invalid email or password. Use the credentials shown below.'
        : msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const fillDemo = () => {
    setEmail(DEMO_EMAIL)
    setPassword(DEMO_PASSWORD)
    setError(null)
  }

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center p-6">
      <Card className="w-full max-w-md bg-[#0f172a] border-[#1e293b]">
        <CardContent className="p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-[#4361ee] rotate-45 flex items-center justify-center">
              <Shield className="w-6 h-6 text-white -rotate-45" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Erasys ClearFrame</h1>
              <p className="text-sm text-gray-400">AI Governance and Safety Platform</p>
            </div>
          </div>

          {reachable === false && (
            <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm">
              <p className="font-medium text-amber-300 mb-2 flex items-center gap-2">
                <Server className="w-4 h-4" /> Connect a backend
              </p>
              <p className="text-gray-400 text-xs mb-3">
                This frontend can't reach an API. Deploy the backend (one-click on Render — see the repo),
                then paste its URL here. Leave blank to use the same origin.
              </p>
              <div className="flex gap-2">
                <Input value={backend} onChange={(e) => setBackendUrl(e.target.value)}
                  placeholder="https://your-backend.onrender.com"
                  className="bg-[#1e293b] border-[#334155] text-xs" />
                <Button type="button" size="sm" onClick={saveBackend} className="bg-amber-500/80 hover:bg-amber-500 shrink-0">
                  Connect
                </Button>
              </div>
            </div>
          )}

          {isProduction && (
            <div className="mb-6 p-4 bg-[#4361ee]/10 border border-[#4361ee]/30 rounded-lg text-sm">
              <p className="font-medium text-[#93b4ff] mb-2">Demo access credentials</p>
              <p className="text-gray-300 font-mono text-xs">Email: {DEMO_EMAIL}</p>
              <p className="text-gray-300 font-mono text-xs">Password: {DEMO_PASSWORD}</p>
              <p className="text-amber-400/90 text-xs mt-3">
                Access: <strong className="font-mono">http://{typeof window !== 'undefined' ? window.location.host : '18.234.118.78'}</strong> — use <strong>HTTP</strong> (not HTTPS) to avoid browser certificate warnings on this demo host.
              </p>
              <Button type="button" variant="outline" size="sm" className="mt-3 w-full border-[#4361ee]/40 text-[#93b4ff]"
                onClick={fillDemo}>
                Fill credentials
              </Button>
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="text-sm text-gray-400 mb-1 block">Email</label>
              <Input type="email" value={email} onChange={(e) => { setEmail(e.target.value); setError(null) }}
                className="bg-[#1e293b] border-[#334155]" required autoComplete="username" />
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-1 block">Password</label>
              <Input type="password" value={password} onChange={(e) => { setPassword(e.target.value); setError(null) }}
                className="bg-[#1e293b] border-[#334155]" required autoComplete="current-password" />
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" disabled={loading} className="w-full bg-[#4361ee] hover:bg-[#3651d4] gap-2">
              <LogIn className="w-4 h-4" /> {loading ? 'Signing in...' : 'Sign In'}
            </Button>
            {ssoAvailable && (
              <Button type="button" variant="outline" disabled={loading} className="w-full border-[#334155] gap-2"
                onClick={async () => { setLoading(true); try { await loginWithSso() } catch (e) { toast.error(e instanceof Error ? e.message : 'SSO failed'); setLoading(false) } }}>
                Sign in with SSO
              </Button>
            )}
          </form>

          {!ssoAvailable && !isProduction && (
            <div className="mt-6 p-4 bg-[#1e293b]/50 rounded-lg text-xs text-gray-500 space-y-1">
              <p className="font-medium text-gray-400 mb-2">Demo accounts:</p>
              <p>admin@erasys.local / admin</p>
              <p>operator@erasys.local / operator</p>
              <p>auditor@erasys.local / auditor</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
