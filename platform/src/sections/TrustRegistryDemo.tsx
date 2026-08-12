import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Database, Plus, Trash2, AlertTriangle, CheckCircle, Shield } from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'
import type { CertTrustLevel } from '@/lib/sandbox-types'

interface TrustRegistryDemoProps {
  compact?: boolean
}

export function TrustRegistryDemo({ compact }: TrustRegistryDemoProps) {
  const { agents, currentAgent, operator, cert, registerAgentInRegistry, revokeAgent, issueCertificate, verifyCertificate, revokeCertificate, selectAgent } = useSandbox()
  const [newAgentName, setNewAgentName] = useState('')
  const [newAgentRole, setNewAgentRole] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [trustLevel, setTrustLevel] = useState<CertTrustLevel>('STANDARD')
  const [ttlHours, setTtlHours] = useState(24)

  const registerAgent = async () => {
    if (!newAgentName || !newAgentRole) {
      toast.error('Please provide agent name and role')
      return
    }
    try {
      const agent = await registerAgentInRegistry(newAgentName, newAgentRole)
    setNewAgentName('')
    setNewAgentRole('')
    setShowForm(false)
      toast.success(`Agent "${agent.name}" registered with ID ${agent.agentId}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Registration failed')
    }
  }

  const handleIssueCert = async () => {
    try {
      const result = await issueCertificate(trustLevel, ttlHours)
      if (result.ok) toast.success(result.message)
      else toast.error(result.message)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Issue failed')
    }
  }

  const handleVerifyCert = async () => {
    const result = await verifyCertificate()
    if (result.ok) toast.success(result.message)
    else toast.error(result.message)
  }

  const handleRevokeCert = async () => {
    const result = await revokeCertificate()
    if (result.ok) toast.warning(result.message)
    else toast.error(result.message)
  }

  const statusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'suspended':
        return <AlertTriangle className="w-4 h-4 text-yellow-400" />
      case 'revoked':
        return <Trash2 className="w-4 h-4 text-red-400" />
      default:
        return null
    }
  }

  if (compact) {
    return (
      <Card className="bg-[#0f172a] border-[#1e293b] hover:border-purple-500/50 transition-colors h-full">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-purple-500 flex items-center justify-center">
              <Database className="w-4 h-4 text-white" />
            </div>
            <CardTitle className="text-sm">TrustRegistry</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-gray-400 mb-3">{agents.length} agents registered</p>
          <div className="flex gap-2">
            <Badge className="bg-green-500/20 text-green-400 text-xs">{agents.filter((a) => a.status === 'active').length} Active</Badge>
            <Badge className="bg-yellow-500/20 text-yellow-400 text-xs">{agents.filter((a) => a.status === 'suspended').length} Suspended</Badge>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-purple-500 flex items-center justify-center">
          <Database className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">TrustRegistry</h2>
          <p className="text-sm text-gray-400">Agent Identity & Registration — IS the agent trusted?</p>
        </div>
        <Badge className="ml-auto bg-purple-500/20 text-purple-400 border-purple-500/30">Identity Layer</Badge>
      </div>

      {!operator?.verified && (
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-sm text-yellow-400">
          Complete SafePulse authentication before issuing certificates.
        </div>
      )}

      <Card className="bg-[#0f172a] border-[#1e293b] mb-4">
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">Registered Agents ({agents.length})</h3>
            <Button size="sm" onClick={() => setShowForm(!showForm)} className="bg-purple-500 hover:bg-purple-600 gap-2">
              <Plus className="w-4 h-4" /> Register Agent
            </Button>
          </div>
          {showForm && (
            <div className="mb-4 p-4 bg-[#1e293b] rounded-lg space-y-3">
              <Input placeholder="Agent name (e.g., MyAgent)" value={newAgentName} onChange={(e) => setNewAgentName(e.target.value)} className="bg-[#0f172a] border-[#334155]" />
              <Select value={newAgentRole} onValueChange={setNewAgentRole}>
                <SelectTrigger className="bg-[#0f172a] border-[#334155]">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="code-review">Code Review</SelectItem>
                  <SelectItem value="data-analysis">Data Analysis</SelectItem>
                  <SelectItem value="customer-support">Customer Support</SelectItem>
                  <SelectItem value="security-scan">Security Scan</SelectItem>
                  <SelectItem value="devops">DevOps</SelectItem>
                </SelectContent>
              </Select>
              <div className="flex gap-2">
                <Button onClick={registerAgent} className="bg-purple-500 hover:bg-purple-600">
                  Register
                </Button>
                <Button variant="outline" onClick={() => setShowForm(false)} className="border-[#334155]">
                  Cancel
                </Button>
              </div>
            </div>
          )}
          <div className="space-y-2">
            {agents.map((agent) => (
              <div
                key={agent.agentId}
                onClick={() => selectAgent(agent.agentId)}
                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer ${currentAgent?.agentId === agent.agentId ? 'bg-purple-500/10 border border-purple-500/30' : 'bg-[#1e293b]/50 hover:bg-[#1e293b]'}`}
              >
                {statusIcon(agent.status)}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{agent.name}</p>
                  <p className="text-xs text-gray-500">
                    {agent.agentId} · {agent.capabilities.join(', ') || 'no caps'} · {agent.owner}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-sm font-mono">{agent.trustScore}%</div>
                  <Badge
                    className={`text-xs ${
                      agent.status === 'active'
                        ? 'bg-green-500/20 text-green-400'
                        : agent.status === 'suspended'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-red-500/20 text-red-400'
                    }`}
                  >
                    {agent.status}
                  </Badge>
                </div>
                {agent.status !== 'revoked' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => {
                      e.stopPropagation()
                      revokeAgent(agent.agentId)
                      toast.warning(`Agent ${agent.agentId} revoked`)
                    }}
                    className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-[#0f172a] border-[#1e293b]">
        <CardContent className="p-6 space-y-4">
          <h3 className="font-semibold flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-400" /> Certificate Management
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select value={trustLevel} onValueChange={(v) => setTrustLevel(v as CertTrustLevel)}>
              <SelectTrigger className="bg-[#1e293b] border-[#334155]">
                <SelectValue placeholder="Trust level" />
              </SelectTrigger>
              <SelectContent>
                {(['SANDBOX', 'RESTRICTED', 'STANDARD', 'ELEVATED', 'CRITICAL'] as CertTrustLevel[]).map((level) => (
                  <SelectItem key={level} value={level}>
                    {level}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div>
              <label className="text-xs text-gray-400">TTL: {ttlHours}h</label>
              <input type="range" min={1} max={168} value={ttlHours} onChange={(e) => setTtlHours(Number(e.target.value))} className="w-full" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleIssueCert} className="bg-purple-500 hover:bg-purple-600">Issue Certificate</Button>
            <Button variant="outline" onClick={handleVerifyCert} className="border-[#334155]">Verify</Button>
            <Button variant="outline" onClick={handleRevokeCert} className="border-red-500/30 text-red-400">Revoke</Button>
          </div>
          {cert && (
            <div className="p-3 bg-[#1e293b] rounded-lg font-mono text-xs text-gray-300 space-y-1">
              <p>ID: {cert.certId}</p>
              <p>Agent: {cert.agentId}</p>
              <p>Level: {cert.trustLevel}</p>
              <p>Revoked: {cert.revoked ? 'yes' : 'no'}</p>
              <p className="truncate">Sig: {cert.signature}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
