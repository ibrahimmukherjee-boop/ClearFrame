import { useState, useRef, useCallback, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Fingerprint, Shield, AlertTriangle, CheckCircle, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'

interface SafePulseDemoProps {
  compact?: boolean
}

interface KeystrokeEvent {
  key: string
  timestamp: number
  type: 'down' | 'up'
}

export function SafePulseDemo({ compact }: SafePulseDemoProps) {
  const { safepulseEnrolled, operator, enrollSafepulse, verifySafepulse, resetSafepulse } = useSandbox()
  const [isAuthenticating, setIsAuthenticating] = useState(false)
  const [trustScore, setTrustScore] = useState(operator ? Math.round(operator.trustScore * 100) : 0)
  const [status, setStatus] = useState<'idle' | 'enrolling' | 'enrolled' | 'verifying' | 'authenticated' | 'rejected'>(
    operator?.verified ? 'authenticated' : safepulseEnrolled ? 'enrolled' : 'idle',
  )
  const [keystrokes, setKeystrokes] = useState<KeystrokeEvent[]>([])
  const [inputText, setInputText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' || e.key === 'Enter') return
    setKeystrokes((prev) => [...prev, { key: e.key, timestamp: Date.now(), type: 'down' }])
  }, [])

  const handleKeyUp = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' || e.key === 'Enter') return
    setKeystrokes((prev) => [...prev, { key: e.key, timestamp: Date.now(), type: 'up' }])
  }, [])

  const extractProfile = (events: KeystrokeEvent[]): number[] => {
    const downEvents = events.filter((e) => e.type === 'down')
    const upEvents = events.filter((e) => e.type === 'up')
    const features: number[] = []
    for (let i = 1; i < downEvents.length; i++) {
      features.push(downEvents[i].timestamp - downEvents[i - 1].timestamp)
    }
    for (let i = 0; i < Math.min(downEvents.length, upEvents.length); i++) {
      const upEvent = upEvents.find((e) => e.key === downEvents[i].key && e.timestamp > downEvents[i].timestamp)
      if (upEvent) features.push(upEvent.timestamp - downEvents[i].timestamp)
    }
    return features.slice(0, 20)
  }

  const startEnrollment = () => {
    setStatus('enrolling')
    setKeystrokes([])
    setInputText('')
    toast.info('Type the phrase "Secure the agentic future" to enroll your biometric profile')
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  const verifyTyping = useCallback(async () => {
    if (inputText.length < 10) return
    const newProfile = extractProfile(keystrokes)
    if (status === 'enrolling') {
      try {
        await enrollSafepulse(newProfile)
        setStatus('enrolled')
        setTrustScore(100)
        toast.success('Biometric profile enrolled successfully!')
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Enrollment failed')
      }
    } else if (status === 'enrolled' || status === 'authenticated' || status === 'rejected') {
      setStatus('verifying')
      setIsAuthenticating(true)
      try {
        const { success, score } = await verifySafepulse(newProfile)
        setTrustScore(score)
        setIsAuthenticating(false)
        if (success) {
          setStatus('authenticated')
          toast.success(`Authentication successful! Trust score: ${score}%`)
        } else {
          setStatus('rejected')
          toast.error(`Authentication failed! Trust score: ${score}%`)
        }
      } catch (e) {
        setIsAuthenticating(false)
        toast.error(e instanceof Error ? e.message : 'Verification failed')
      }
    }
  }, [inputText, keystrokes, status, enrollSafepulse, verifySafepulse])

  useEffect(() => {
    if (inputText.length >= 30) verifyTyping()
  }, [inputText, verifyTyping])

  const reset = () => {
    resetSafepulse()
    setIsAuthenticating(false)
    setTrustScore(0)
    setStatus('idle')
    setKeystrokes([])
    setInputText('')
  }

  const statusConfig = {
    idle: { color: 'text-gray-400', bg: 'bg-gray-500/10', icon: <Fingerprint className="w-5 h-5" />, text: 'Not enrolled' },
    enrolling: { color: 'text-blue-400', bg: 'bg-blue-500/10', icon: <Fingerprint className="w-5 h-5 animate-pulse" />, text: 'Enrolling...' },
    enrolled: { color: 'text-green-400', bg: 'bg-green-500/10', icon: <CheckCircle className="w-5 h-5" />, text: 'Profile enrolled' },
    verifying: { color: 'text-yellow-400', bg: 'bg-yellow-500/10', icon: <Fingerprint className="w-5 h-5 animate-spin" />, text: 'Verifying...' },
    authenticated: { color: 'text-green-400', bg: 'bg-green-500/10', icon: <Shield className="w-5 h-5" />, text: 'Authenticated' },
    rejected: { color: 'text-red-400', bg: 'bg-red-500/10', icon: <AlertTriangle className="w-5 h-5" />, text: 'Rejected' },
  }

  const currentStatus = statusConfig[status]

  if (compact) {
    return (
      <Card className="bg-[#0f172a] border-[#1e293b] hover:border-[#4361ee]/50 transition-colors h-full">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center">
              <Fingerprint className="w-4 h-4 text-white" />
            </div>
            <CardTitle className="text-sm">SafePulse</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-gray-400 mb-3">Behavioral biometric authentication via typing patterns</p>
          <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${currentStatus.bg} ${currentStatus.color}`}>
            {currentStatus.icon}
            {currentStatus.text}
          </div>
          {trustScore > 0 && (
            <div className="mt-3">
              <Progress value={trustScore} className="h-1.5" />
              <p className="text-xs text-gray-500 mt-1">Trust: {trustScore}%</p>
            </div>
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-blue-500 flex items-center justify-center">
          <Fingerprint className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">SafePulse</h2>
          <p className="text-sm text-gray-400">Behavioral Biometric Authentication — WHO is the operator?</p>
        </div>
        <Badge className="ml-auto bg-blue-500/20 text-blue-400 border-blue-500/30">Intent-Based Access Control</Badge>
      </div>
      <Card className="bg-[#0f172a] border-[#1e293b]">
        <CardContent className="p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${currentStatus.bg} ${currentStatus.color}`}>
              {currentStatus.icon}
              {currentStatus.text}
            </div>
            {trustScore > 0 && (
              <div className="text-right">
                <p className="text-2xl font-bold text-[#4361ee]">{trustScore}%</p>
                <p className="text-xs text-gray-500">Trust Score</p>
              </div>
            )}
          </div>
          {trustScore > 0 && <Progress value={trustScore} className="h-2" />}
          <div className="space-y-2">
            <label className="text-sm text-gray-400">
              {status === 'enrolling' ? 'Type to create your biometric profile:' : 'Type to verify your identity:'}
            </label>
            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              onKeyUp={handleKeyUp}
              placeholder={status === 'idle' ? 'Click "Enroll" to begin...' : 'Type "Secure the agentic future"...'}
              disabled={status === 'idle' || status === 'verifying'}
              className="w-full px-4 py-3 bg-[#1e293b] border border-[#334155] rounded-lg text-white placeholder:text-gray-600 focus:outline-none focus:border-[#4361ee] disabled:opacity-50"
            />
            <p className="text-xs text-gray-500">Keystrokes captured: {keystrokes.length}</p>
          </div>
          <div className="flex gap-3">
            {status === 'idle' && (
              <Button onClick={startEnrollment} className="bg-blue-500 hover:bg-blue-600 gap-2">
                <Fingerprint className="w-4 h-4" /> Enroll Profile
              </Button>
            )}
            {(status === 'enrolled' || status === 'authenticated' || status === 'rejected') && (
              <Button
                onClick={() => {
                  setStatus('enrolled')
                  setKeystrokes([])
                  setInputText('')
                  setTimeout(() => inputRef.current?.focus(), 100)
                }}
                className="bg-blue-500 hover:bg-blue-600 gap-2"
              >
                <Fingerprint className="w-4 h-4" /> Re-Authenticate
              </Button>
            )}
            {status !== 'idle' && (
              <Button variant="outline" onClick={reset} className="border-[#334155] hover:bg-[#1e293b] gap-2">
                <RotateCcw className="w-4 h-4" /> Reset
              </Button>
            )}
          </div>
          {isAuthenticating && (
            <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
              <p className="text-sm text-yellow-400 flex items-center gap-2">
                <Fingerprint className="w-4 h-4 animate-spin" /> Analyzing keystroke dynamics...
              </p>
            </div>
          )}
          {status === 'authenticated' && (
            <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
              <p className="text-sm text-green-400 flex items-center gap-2">
                <Shield className="w-4 h-4" /> Access granted. Operator verified — proceed to TrustRegistry.
              </p>
            </div>
          )}
          {status === 'rejected' && (
            <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <p className="text-sm text-red-400 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Access denied. Typing pattern mismatch detected.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
