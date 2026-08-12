import { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Eye, Lock, FileText, Terminal, Play, Shield, Target, TrendingUp, AlertTriangle, CheckCircle2, PauseCircle } from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'

export function ClearFrameDemo() {
  const { auditLog, session, currentAgent, operator, cert, startAgentSession } = useSandbox()
  const [isRunning, setIsRunning] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [vaultUnlocked, setVaultUnlocked] = useState(false)

  const runSimulation = async () => {
    try {
      const result = await startAgentSession()
      if (!result.ok) {
        toast.error(result.message)
        return
      }
      setIsRunning(true)
      setCurrentStep(0)
      toast.info('Starting ClearFrame agent session...')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Session failed')
    }
  }

  const entries = auditLog.length > 0 ? auditLog : []

  // Goal Monitor: derive a what / why / how reasoning breakdown for each
  // governed step from its tool, alignment score, and disposition.
  const goal = currentAgent?.description || currentAgent?.name || 'No goal declared yet'
  const avgAlignment = entries.length
    ? Math.round(entries.reduce((s, e) => s + (e.alignment || 0), 0) / entries.length)
    : 0
  const deviations = entries.filter((e) => e.status === 'blocked' || (e.alignment ?? 100) < 60).length
  const goalStatus = deviations > 0 ? 'deviated' : entries.length ? 'on_track' : 'idle'

  const reason = (e: (typeof entries)[number]) => {
    if (e.status === 'blocked')
      return {
        why: `Policy denied this call — it fell outside the declared goal scope (alignment ${e.alignment}%).`,
        how: 'Refused before the Actor sandbox; nothing executed. Recorded in the HMAC audit chain.',
      }
    if (e.status === 'human_review' || e.status === 'flagged')
      return {
        why: `Sensitive action — alignment ${e.alignment}% is below the auto-approve threshold, so a human decision was required.`,
        how: 'Paused fail-closed and queued for Aegis; the pending→decided transition is audited.',
      }
    return {
      why: `Aligned with the goal (alignment ${e.alignment}%) — within manifest scope and policy.`,
      how: 'Executed in the isolated Actor sandbox; result hashed into the audit chain.',
    }
  }

  useEffect(() => {
    if (!isRunning || entries.length === 0) return
    let step = 0
    const interval = setInterval(() => {
      step++
      setCurrentStep(step)
      if (step >= entries.length) {
        clearInterval(interval)
        setIsRunning(false)
        toast.success('Agent session completed.')
      }
    }, 1200)
    return () => clearInterval(interval)
  }, [isRunning, entries.length])

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-green-500 flex items-center justify-center">
          <Eye className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">ClearFrame</h2>
          <p className="text-sm text-gray-400">Runtime Safety & Audit — WHAT is the agent doing?</p>
        </div>
        <Badge className="ml-auto bg-green-500/20 text-green-400 border-green-500/30">Runtime Layer</Badge>
      </div>

      {(!currentAgent || !operator?.verified || !cert || cert.revoked) && (
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-sm text-yellow-400">
          Prerequisites: define an agent (Builder), authenticate (SafePulse), and issue a certificate (TrustRegistry).
        </div>
      )}

      <Tabs defaultValue="goals" className="w-full">
        <TabsList className="bg-[#1e293b] border-[#334155]">
          <TabsTrigger value="goals" className="gap-2">
            <Target className="w-4 h-4" /> Goal Monitor
          </TabsTrigger>
          <TabsTrigger value="audit" className="gap-2">
            <FileText className="w-4 h-4" /> Audit Log
          </TabsTrigger>
          <TabsTrigger value="vault" className="gap-2">
            <Lock className="w-4 h-4" /> Vault
          </TabsTrigger>
          <TabsTrigger value="isolation" className="gap-2">
            <Shield className="w-4 h-4" /> Isolation
          </TabsTrigger>
        </TabsList>

        <TabsContent value="goals">
          <Card className="glass-panel border-transparent overflow-hidden">
            <CardContent className="p-6">
              {/* Goal header + live alignment summary */}
              <div className="flex flex-col md:flex-row md:items-center gap-4 mb-6">
                <div className="flex-1">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-gray-500 mb-1">Declared goal</p>
                  <p className="text-lg font-medium leading-snug text-gray-100">{goal}</p>
                </div>
                <div className="flex items-center gap-5">
                  <div className="text-center">
                    <div className="text-3xl font-semibold tabular-nums">{avgAlignment}<span className="text-base text-gray-500">%</span></div>
                    <p className="text-[10px] uppercase tracking-[0.14em] text-gray-500 mt-1">Mean alignment</p>
                  </div>
                  <div
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
                      goalStatus === 'deviated'
                        ? 'bg-white/10 text-gray-200'
                        : goalStatus === 'on_track'
                          ? 'bg-white/5 text-gray-300'
                          : 'bg-white/5 text-gray-500'
                    }`}
                  >
                    {goalStatus === 'deviated' ? <AlertTriangle className="w-3.5 h-3.5" /> : goalStatus === 'on_track' ? <TrendingUp className="w-3.5 h-3.5" /> : <PauseCircle className="w-3.5 h-3.5" />}
                    {goalStatus === 'deviated' ? `${deviations} deviation${deviations > 1 ? 's' : ''}` : goalStatus === 'on_track' ? 'On track' : 'Idle'}
                  </div>
                  <Button onClick={runSimulation} disabled={isRunning} className="bg-white/10 hover:bg-white/20 text-white gap-2 backdrop-blur">
                    <Play className="w-4 h-4" /> {isRunning ? 'Running…' : 'Run Agent'}
                  </Button>
                </div>
              </div>

              {entries.length === 0 ? (
                <p className="text-sm text-gray-500 py-8 text-center">
                  No reasoning steps yet. Run an agent session — every tool call will be scored for goal
                  alignment and explained below (what · why · how).
                </p>
              ) : (
                <div className="space-y-3">
                  {entries.map((e, i) => {
                    const r = reason(e)
                    const active = !isRunning || i <= currentStep
                    const low = (e.alignment ?? 100) < 60
                    return (
                      <div
                        key={e.id}
                        className={`glass-panel rounded-2xl p-4 transition-all duration-500 ${active ? 'opacity-100' : 'opacity-30'}`}
                      >
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-7 h-7 rounded-lg bg-white/5 grid place-items-center text-[11px] font-mono text-gray-400">
                            {i + 1}
                          </div>
                          <span className="font-mono text-sm text-gray-200">{e.tool}</span>
                          <span className="ml-auto flex items-center gap-1.5 text-xs text-gray-400">
                            {e.status === 'blocked' ? <AlertTriangle className="w-3.5 h-3.5" /> : e.status === 'human_review' || e.status === 'flagged' ? <PauseCircle className="w-3.5 h-3.5" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                            {e.status}
                          </span>
                        </div>

                        {/* Alignment meter */}
                        <div className="flex items-center gap-3 mb-3">
                          <div className="align-track flex-1 h-1.5">
                            <div className="align-fill" style={{ width: `${Math.max(4, e.alignment ?? 0)}%`, background: low ? 'linear-gradient(90deg, rgba(120,120,120,0.5), rgba(180,180,180,0.7))' : undefined }} />
                          </div>
                          <span className="text-xs tabular-nums text-gray-400 w-10 text-right">{e.alignment}%</span>
                        </div>

                        {/* What / Why / How */}
                        <dl className="grid gap-1.5 text-sm">
                          <div className="flex gap-2">
                            <dt className="text-[10px] uppercase tracking-[0.14em] text-gray-500 w-12 pt-0.5">What</dt>
                            <dd className="flex-1 text-gray-200">{e.action}</dd>
                          </div>
                          <div className="flex gap-2">
                            <dt className="text-[10px] uppercase tracking-[0.14em] text-gray-500 w-12 pt-0.5">Why</dt>
                            <dd className="flex-1 text-gray-400 border-l border-white/10 pl-2.5">{r.why}</dd>
                          </div>
                          <div className="flex gap-2">
                            <dt className="text-[10px] uppercase tracking-[0.14em] text-gray-500 w-12 pt-0.5">How</dt>
                            <dd className="flex-1 text-gray-500">{r.how}</dd>
                          </div>
                        </dl>
                      </div>
                    )
                  })}
                  <p className="text-xs text-gray-500 flex items-center gap-2 pt-1">
                    <Terminal className="w-3 h-3" />
                    Alignment scored by the ClearFrame Goal Monitor; drift below 60% auto-pauses for human review.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="audit">
          <Card className="bg-[#0f172a] border-[#1e293b]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">HMAC-Chained Audit Trail</h3>
                <Button onClick={runSimulation} disabled={isRunning} className="bg-green-500 hover:bg-green-600 gap-2">
                  <Play className="w-4 h-4" /> {isRunning ? 'Running...' : 'Run Agent'}
                </Button>
              </div>
              {session && (
                <p className="text-xs text-green-400 mb-3">Active session: {session.sessionId} ({session.status})</p>
              )}
              <div className="space-y-2 font-mono text-sm">
                {entries.length === 0 && !isRunning && (
                  <p className="text-gray-500 text-sm">No audit entries yet. Run an agent session to populate the log.</p>
                )}
                {entries.map((entry, i) => (
                  <div
                    key={entry.id}
                    className={`flex items-center gap-3 p-3 rounded-lg transition-all duration-500 ${i <= currentStep && isRunning ? 'bg-[#1e293b] opacity-100' : 'opacity-30'} ${!isRunning ? 'bg-[#1e293b]/50 opacity-100' : ''}`}
                  >
                    <span className="text-gray-500 text-xs w-16">{entry.timestamp}</span>
                    <Badge
                      className={`text-xs ${
                        entry.status === 'allowed'
                          ? 'bg-green-500/20 text-green-400'
                          : entry.status === 'blocked'
                            ? 'bg-red-500/20 text-red-400'
                            : 'bg-yellow-500/20 text-yellow-400'
                      }`}
                    >
                      {entry.status}
                    </Badge>
                    <span className="flex-1 truncate">{entry.action}</span>
                    <span className="text-xs text-gray-500">{entry.alignment}% align</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 p-3 bg-[#1e293b] rounded-lg">
                <p className="text-xs text-gray-400 flex items-center gap-2">
                  <Terminal className="w-3 h-3" />
                  <code>clearframe audit-verify</code> — Tamper-evident HMAC chain verified
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="vault">
          <Card className="bg-[#0f172a] border-[#1e293b]">
            <CardContent className="p-6 space-y-4">
              <h3 className="font-semibold">Encrypted Credential Vault (AES-256-GCM)</h3>
              <div className="space-y-3">
                {['OPENAI_API_KEY', 'DATABASE_URL', 'AWS_ACCESS_KEY'].map((key) => (
                  <div key={key} className="flex items-center gap-3 p-3 bg-[#1e293b] rounded-lg">
                    <Lock className="w-4 h-4 text-green-400" />
                    <span className="font-mono text-sm flex-1">{key}</span>
                    <span className="text-xs text-gray-500">{vaultUnlocked ? 'sk-•••••••••••••••' : '•••••••••••••••••••'}</span>
                  </div>
                ))}
              </div>
              <Button
                onClick={() => {
                  setVaultUnlocked(!vaultUnlocked)
                  toast.info(vaultUnlocked ? 'Vault locked' : 'Vault unlocked')
                }}
                className={vaultUnlocked ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'}
              >
                <Lock className="w-4 h-4 mr-2" /> {vaultUnlocked ? 'Lock Vault' : 'Unlock Vault'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="isolation">
          <Card className="bg-[#0f172a] border-[#1e293b]">
            <CardContent className="p-6">
              <h3 className="font-semibold mb-4">Reader/Actor Process Isolation</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                  <h4 className="text-blue-400 font-medium mb-2">Reader Sandbox</h4>
                  <p className="text-xs text-gray-400">Untrusted content only. Never executes tools. Reads raw input, passes typed data to Actor.</p>
                </div>
                <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
                  <h4 className="text-green-400 font-medium mb-2">Actor Sandbox</h4>
                  <p className="text-xs text-gray-400">Tool execution only. Never reads raw input. Receives typed data via secure pipe.</p>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-center">
                <div className="px-4 py-2 bg-[#1e293b] rounded text-xs text-gray-400 font-mono">Typed Pipe (sandboxed IPC)</div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </section>
  )
}
