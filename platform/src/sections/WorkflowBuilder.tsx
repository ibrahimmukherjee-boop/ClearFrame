import { useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { GitBranch, Play, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useSandbox } from '@/lib/sandbox-store'

export function WorkflowBuilder() {
  const { agents, refresh } = useSandbox()
  const [name, setName] = useState('')
  const [workflows, setWorkflows] = useState<Array<Record<string, unknown>>>([])
  const [steps, setSteps] = useState([{ agentId: '', goal: '', maxSteps: 5 }])

  const loadWorkflows = async () => {
    const wfs = await api.listWorkflows()
    setWorkflows(wfs)
  }

  useEffect(() => { loadWorkflows().catch(() => {}) }, [])

  const addStep = () => setSteps([...steps, { agentId: '', goal: '', maxSteps: 5 }])

  const handleCreate = async () => {
    if (!name.trim()) return
    try {
      await api.createWorkflow({ name, description: 'Multi-agent workflow', steps })
      toast.success(`Workflow "${name}" created`)
      await loadWorkflows()
      await refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed')
    }
  }

  const handleRun = async (id: string) => {
    try {
      const result = await api.runWorkflow(id)
      toast.success(`Workflow completed: ${result.runId}`)
      await refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Run failed')
    }
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-teal-600 flex items-center justify-center">
          <GitBranch className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Workflow Orchestrator</h2>
          <p className="text-sm text-gray-400">Multi-agent pipelines with governed execution</p>
        </div>
      </div>

      <Card className="bg-[#0f172a] border-[#1e293b] mb-6">
        <CardContent className="p-6 space-y-4">
          <Input placeholder="Workflow name" value={name} onChange={(e) => setName(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
          {steps.map((step, i) => (
            <div key={i} className="grid grid-cols-2 gap-3 p-3 bg-[#1e293b]/50 rounded">
              <select value={step.agentId} onChange={(e) => { const s = [...steps]; s[i].agentId = e.target.value; setSteps(s) }} className="bg-[#1e293b] border border-[#334155] rounded px-2 text-sm">
                <option value="">Current agent</option>
                {agents.map((a) => <option key={a.agentId} value={a.agentId}>{a.name}</option>)}
              </select>
              <Input placeholder="Goal / task" value={step.goal} onChange={(e) => { const s = [...steps]; s[i].goal = e.target.value; setSteps(s) }} className="bg-[#1e293b] border-[#334155]" />
            </div>
          ))}
          <div className="flex gap-2">
            <Button variant="outline" onClick={addStep} className="border-[#334155] gap-1"><Plus className="w-4 h-4" /> Step</Button>
            <Button onClick={handleCreate} className="bg-teal-600 hover:bg-teal-700">Create Workflow</Button>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {workflows.map((wf) => (
          <Card key={wf.workflowId as string} className="bg-[#0f172a] border-[#1e293b]">
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <p className="font-medium">{wf.name as string}</p>
                <p className="text-xs text-gray-500">{(wf.steps as unknown[])?.length || 0} steps</p>
              </div>
              <Button size="sm" onClick={() => handleRun(wf.workflowId as string)} className="bg-teal-600 gap-1">
                <Play className="w-3 h-3" /> Run
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}
