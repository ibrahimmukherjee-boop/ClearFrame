import { useState, useRef } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Workflow, Fingerprint, Database, Eye, Crosshair, Radar, Bot, Play, CheckCircle, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'
import type { PipelineStepState } from '@/lib/sandbox-types'

const STEP_META = [
  { id: 'builder', name: 'Agent Builder', icon: <Bot className="w-5 h-5" />, color: 'bg-[#4361ee]', description: 'Defining agent configuration...' },
  { id: 'safepulse', name: 'SafePulse', icon: <Fingerprint className="w-5 h-5" />, color: 'bg-blue-500', description: 'Authenticating operator...' },
  { id: 'trustregistry', name: 'TrustRegistry', icon: <Database className="w-5 h-5" />, color: 'bg-purple-500', description: 'Issuing trust certificate...' },
  { id: 'clearframe', name: 'ClearFrame', icon: <Eye className="w-5 h-5" />, color: 'bg-green-500', description: 'Initializing runtime sandbox...' },
  { id: 'aegis', name: 'Aegis', icon: <Crosshair className="w-5 h-5" />, color: 'bg-orange-500', description: 'Loading Goal Manifest...' },
  { id: 'sonar', name: 'Sonar', icon: <Radar className="w-5 h-5" />, color: 'bg-red-500', description: 'Starting threat monitoring...' },
]

export function FullPipelineDemo() {
  const { runFullPipeline, pipelineLog } = useSandbox()
  const [steps, setSteps] = useState<PipelineStepState[]>(STEP_META.map((s) => ({ ...s, status: 'pending' as const })))
  const [isRunning, setIsRunning] = useState(false)
  const [overallProgress, setOverallProgress] = useState(0)
  const cleanupRef = useRef<(() => void) | null>(null)

  const runPipeline = () => {
    setIsRunning(true)
    setOverallProgress(0)
    setSteps(STEP_META.map((s) => ({ id: s.id, name: s.name, status: 'pending', description: s.description })))
    toast.info('Starting full Erasys pipeline...')

    cleanupRef.current?.()
    cleanupRef.current = runFullPipeline(
      (updated) => {
        setSteps(updated)
        const complete = updated.filter((s) => s.status === 'complete').length
        setOverallProgress((complete / updated.length) * 100)
      },
      (success) => {
        setIsRunning(false)
        if (success) toast.success('Full pipeline executed successfully!')
        else toast.error('Pipeline failed — check prerequisites in each step tab.')
      },
    )
  }

  const statusIcon = (status: string) => {
    switch (status) {
      case 'complete':
        return <CheckCircle className="w-5 h-5 text-green-400" />
      case 'running':
        return <Workflow className="w-5 h-5 text-blue-400 animate-spin" />
      case 'failed':
        return <AlertTriangle className="w-5 h-5 text-red-400" />
      default:
        return <div className="w-5 h-5 rounded-full border-2 border-gray-600" />
    }
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[#4361ee] flex items-center justify-center">
          <Workflow className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Full Pipeline</h2>
          <p className="text-sm text-gray-400">Run the complete Erasys trust pipeline end-to-end</p>
        </div>
        <Button onClick={runPipeline} disabled={isRunning} className="ml-auto bg-[#4361ee] hover:bg-[#3651d4] gap-2">
          <Play className="w-4 h-4" /> {isRunning ? 'Running...' : 'Run Pipeline'}
        </Button>
      </div>
      <Card className="bg-[#0f172a] border-[#1e293b]">
        <CardContent className="p-6">
          {isRunning && (
            <div className="mb-6">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">Pipeline Progress</span>
                <span className="text-[#4361ee]">{Math.round(overallProgress)}%</span>
              </div>
              <Progress value={overallProgress} className="h-2" />
            </div>
          )}
          <div className="space-y-3">
            {steps.map((step, i) => {
              const meta = STEP_META[i]
              return (
                <div
                  key={step.id}
                  className={`flex items-center gap-4 p-4 rounded-lg transition-all duration-500 ${
                    step.status === 'running'
                      ? 'bg-[#1e293b] border border-[#4361ee]/30'
                      : step.status === 'complete'
                        ? 'bg-[#1e293b]/50'
                        : step.status === 'failed'
                          ? 'bg-red-500/10 border border-red-500/30'
                          : 'bg-[#1e293b]/20 opacity-60'
                  }`}
                >
                  <div className={`w-10 h-10 rounded-lg ${meta.color} flex items-center justify-center text-white`}>{meta.icon}</div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{step.name}</span>
                      <span className="text-xs text-gray-500 font-mono">0{i + 1}</span>
                    </div>
                    <p className="text-xs text-gray-400">{step.error ?? step.description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {statusIcon(step.status)}
                    <Badge
                      className={`text-xs ${
                        step.status === 'complete'
                          ? 'bg-green-500/20 text-green-400'
                          : step.status === 'running'
                            ? 'bg-blue-500/20 text-blue-400'
                            : step.status === 'failed'
                              ? 'bg-red-500/20 text-red-400'
                              : 'bg-gray-500/20 text-gray-400'
                      }`}
                    >
                      {step.status}
                    </Badge>
                  </div>
                </div>
              )
            })}
          </div>
          {steps.every((s) => s.status === 'complete') && (
            <div className="mt-4 p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-center">
              <CheckCircle className="w-6 h-6 text-green-400 mx-auto mb-2" />
              <p className="text-green-400 font-medium">All layers passed. Agent is fully secured and operational.</p>
            </div>
          )}
          {pipelineLog.length > 0 && (
            <div className="mt-4 p-3 bg-[#1e293b] rounded-lg">
              <p className="text-xs text-gray-500 mb-2 font-semibold uppercase">Pipeline Log</p>
              <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">{pipelineLog.join('\n')}</pre>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
