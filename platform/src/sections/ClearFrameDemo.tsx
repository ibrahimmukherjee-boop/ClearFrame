import { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Eye, Lock, FileText, Terminal, Play, Shield } from 'lucide-react'
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

      <Tabs defaultValue="audit" className="w-full">
        <TabsList className="bg-[#1e293b] border-[#334155]">
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
