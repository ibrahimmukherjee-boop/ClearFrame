import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Bot, Plug, Wrench, Play, Trash2, Pause, Check } from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'
import type { AgentConfig } from '@/lib/sandbox-types'

const statusColors: Record<string, string> = {
  active: 'bg-green-500/20 text-green-400',
  suspended: 'bg-yellow-500/20 text-yellow-400',
  revoked: 'bg-red-500/20 text-red-400',
}

export function AgentManagement() {
  const { agents, currentAgent, selectAgent, suspendAgent, activateAgent, revokeAgent, toolCatalog, toolConnections, createConnection, executeTool, refresh } = useSandbox()
  const [connName, setConnName] = useState('')
  const [selectedTool, setSelectedTool] = useState('')
  const [testResult, setTestResult] = useState<string | null>(null)

  const handleSelect = async (agent: AgentConfig) => {
    try {
      await selectAgent(agent.agentId)
      toast.success(`Selected ${agent.name}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed')
    }
  }

  const handleSuspend = async (agentId: string) => {
    await suspendAgent(agentId)
    toast.info('Agent suspended')
    await refresh()
  }

  const handleActivate = async (agentId: string) => {
    await activateAgent(agentId)
    toast.success('Agent activated')
    await refresh()
  }

  const handleRevoke = async (agentId: string) => {
    await revokeAgent(agentId)
    toast.error('Agent revoked')
    await refresh()
  }

  const handleCreateConnection = async () => {
    if (!selectedTool || !connName.trim()) {
      toast.error('Select a tool and enter a connection name')
      return
    }
    try {
      await createConnection(selectedTool, connName.trim())
      toast.success(`Connection "${connName}" created`)
      setConnName('')
      await refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed')
    }
  }

  const handleTestTool = async (toolId: string) => {
    try {
      const args = toolId === 'web_search' ? { query: 'AI governance ISO 42001' } : toolId === 'shell_exec' ? { command: 'echo hello' } : {}
      const result = await executeTool(toolId, args)
      setTestResult(JSON.stringify(result, null, 2))
      toast.success(`Tool ${toolId} executed`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Tool execution failed')
    }
  }

  return (
    <div className="space-y-6 mt-8">
      <Card className="bg-[#0f172a] border-[#1e293b]">
        <CardContent className="p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Bot className="w-4 h-4 text-[#4361ee]" /> Agent Registry ({agents.length})
          </h3>
          <div className="space-y-3">
            {agents.map((agent) => (
              <div key={agent.agentId} className="flex flex-wrap items-center gap-3 p-4 rounded-lg bg-[#1e293b]/50 border border-[#334155]">
                <div className="flex-1 min-w-[200px]">
                  <div className="flex items-center gap-2">
                    <p className="font-medium">{agent.name}</p>
                    {currentAgent?.agentId === agent.agentId && (
                      <Badge className="bg-[#4361ee]/20 text-[#4361ee] text-[10px]">current</Badge>
                    )}
                  </div>
                  <p className="text-xs text-gray-500">{agent.agentId} · {agent.owner} · trust {agent.trustScore}</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {agent.capabilities.map((c) => (
                      <Badge key={c} variant="outline" className="text-[10px] border-[#334155]">{c}</Badge>
                    ))}
                  </div>
                </div>
                <Badge className={statusColors[agent.status]}>{agent.status}</Badge>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" className="border-[#334155] h-8" onClick={() => handleSelect(agent)}>
                    <Check className="w-3 h-3" />
                  </Button>
                  {agent.status === 'active' ? (
                    <Button size="sm" variant="outline" className="border-[#334155] h-8" onClick={() => handleSuspend(agent.agentId)}>
                      <Pause className="w-3 h-3" />
                    </Button>
                  ) : agent.status === 'suspended' ? (
                    <Button size="sm" variant="outline" className="border-[#334155] h-8" onClick={() => handleActivate(agent.agentId)}>
                      <Play className="w-3 h-3" />
                    </Button>
                  ) : null}
                  <Button size="sm" variant="outline" className="border-red-500/30 text-red-400 h-8" onClick={() => handleRevoke(agent.agentId)}>
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-[#0f172a] border-[#1e293b]">
          <CardContent className="p-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <Plug className="w-4 h-4 text-cyan-400" /> Tool Marketplace
            </h3>
            <div className="space-y-2 max-h-64 overflow-y-auto mb-4">
              {toolCatalog.map((tool) => (
                <button
                  key={tool.id}
                  type="button"
                  onClick={() => setSelectedTool(tool.id)}
                  className={`w-full text-left p-3 rounded border transition-colors ${
                    selectedTool === tool.id ? 'border-cyan-500 bg-cyan-500/10' : 'border-[#334155] hover:border-cyan-500/50'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium">{tool.name}</span>
                    {tool.requiresKey && <Badge className="text-[10px] bg-yellow-500/20 text-yellow-400">API key</Badge>}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{tool.description}</p>
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <Input placeholder="Connection name" value={connName} onChange={(e) => setConnName(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
              <Button onClick={handleCreateConnection} className="bg-cyan-600 hover:bg-cyan-700 shrink-0">Connect</Button>
            </div>
            {toolConnections.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-gray-400 mb-2">Active connections</p>
                {toolConnections.map((c) => (
                  <Badge key={c.connectionId} className="mr-2 mb-1 bg-[#1e293b]">{c.name} ({c.toolId})</Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-[#0f172a] border-[#1e293b]">
          <CardContent className="p-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <Wrench className="w-4 h-4 text-orange-400" /> Tool Sandbox
            </h3>
            <p className="text-sm text-gray-400 mb-4">Test tools before assigning to agents</p>
            <div className="flex flex-wrap gap-2 mb-4">
              {['web_search', 'shell_exec', 'file_write', 'database_read'].map((t) => (
                <Button key={t} size="sm" variant="outline" className="border-[#334155] text-xs" onClick={() => handleTestTool(t)}>
                  {t}
                </Button>
              ))}
            </div>
            {testResult && (
              <pre className="text-xs bg-[#1e293b] p-3 rounded overflow-auto max-h-48 text-green-400">{testResult}</pre>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
