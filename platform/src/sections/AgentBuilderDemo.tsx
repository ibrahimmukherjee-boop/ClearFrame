import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Bot, Save, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'

interface AgentBuilderDemoProps {
  compact?: boolean
}

export function AgentBuilderDemo({ compact }: AgentBuilderDemoProps) {
  const { currentAgent, saveAgent, loadPreset, allCapabilities, presets } = useSandbox()
  const [name, setName] = useState(currentAgent?.name ?? '')
  const [description, setDescription] = useState(currentAgent?.description ?? '')
  const [capabilities, setCapabilities] = useState<string[]>(currentAgent?.capabilities ?? [])
  const [model, setModel] = useState(currentAgent?.model ?? 'llama3')
  const [maxSteps, setMaxSteps] = useState(currentAgent?.maxSteps ?? 10)
  const [allowWeb, setAllowWeb] = useState(currentAgent?.allowWeb ?? false)
  const [allowFs, setAllowFs] = useState(currentAgent?.allowFs ?? false)
  const [allowExec, setAllowExec] = useState(currentAgent?.allowExec ?? false)

  const applyPreset = (presetName: string) => {
    const preset = loadPreset(presetName)
    if (!preset) return
    setName(preset.name)
    setDescription(preset.description)
    setCapabilities(preset.capabilities)
    setModel(preset.model)
    setMaxSteps(preset.maxSteps)
    setAllowWeb(preset.allowWeb)
    setAllowFs(preset.allowFs)
    setAllowExec(preset.allowExec)
    toast.info(`Loaded preset: ${presetName}`)
  }

  const toggleCapability = (cap: string) => {
    setCapabilities((prev) => (prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap]))
  }

  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('Agent name is required')
      return
    }
    setSaving(true)
    try {
      const agent = await saveAgent({
      name: name.trim(),
      description: description.trim(),
      capabilities,
      provider: 'ollama',
      model,
      maxSteps,
      allowWeb,
      allowFs,
      allowExec,
      })
      toast.success(`Agent "${agent.name}" saved (${agent.agentId})`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save agent')
    } finally {
      setSaving(false)
    }
  }

  const resetForm = () => {
    setName('')
    setDescription('')
    setCapabilities([])
    setModel('llama3')
    setMaxSteps(10)
    setAllowWeb(false)
    setAllowFs(false)
    setAllowExec(false)
  }

  if (compact) {
    return (
      <Card className="bg-[#0f172a] border-[#1e293b] hover:border-[#4361ee]/50 transition-colors">
        <CardContent className="p-6 pt-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-[#4361ee] flex items-center justify-center">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <p className="text-sm font-semibold">Agent Builder</p>
          </div>
          <p className="text-xs text-gray-400 mb-3">Define ClearFrame agents with capabilities & scopes</p>
          {currentAgent ? (
            <Badge className="bg-green-500/20 text-green-400 text-xs">{currentAgent.name}</Badge>
          ) : (
            <Badge className="bg-gray-500/20 text-gray-400 text-xs">No agent defined</Badge>
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[#4361ee] flex items-center justify-center">
          <Bot className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Agent Builder</h2>
          <p className="text-sm text-gray-400">Define your ClearFrame agent — name, capabilities, model, and permission scopes</p>
        </div>
        <Badge className="ml-auto bg-[#4361ee]/20 text-[#4361ee] border-[#4361ee]/30">Step 1</Badge>
      </div>

      <Card className="bg-[#0f172a] border-[#1e293b]">
        <CardContent className="p-6 space-y-6">
          <div>
            <label className="text-sm text-gray-400 mb-2 block">Load a preset</label>
            <Select onValueChange={applyPreset}>
              <SelectTrigger className="bg-[#1e293b] border-[#334155]">
                <SelectValue placeholder="Choose a preset..." />
              </SelectTrigger>
              <SelectContent>
                {Object.keys(presets).map((preset) => (
                  <SelectItem key={preset} value={preset}>
                    {preset}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-4">
              <Input placeholder="Agent name" value={name} onChange={(e) => setName(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
              <textarea
                placeholder="Description / goal"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-[#1e293b] border border-[#334155] rounded-md text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#4361ee]"
              />
              <div>
                <p className="text-sm text-gray-400 mb-2">Capabilities</p>
                <div className="flex flex-wrap gap-2">
                  {allCapabilities.map((cap) => (
                    <button
                      key={cap}
                      type="button"
                      onClick={() => toggleCapability(cap)}
                      className={`px-2 py-1 rounded text-xs border transition-colors ${
                        capabilities.includes(cap)
                          ? 'bg-[#4361ee]/20 border-[#4361ee] text-[#4361ee]'
                          : 'bg-[#1e293b] border-[#334155] text-gray-400 hover:border-[#4361ee]/50'
                      }`}
                    >
                      {cap}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="bg-[#1e293b] border-[#334155]">
                  <SelectValue placeholder="Model" />
                </SelectTrigger>
                <SelectContent>
                  {['llama3', 'mistral', 'codellama', 'qwen2', 'gemma2'].map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div>
                <label className="text-sm text-gray-400">Max steps: {maxSteps}</label>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(Number(e.target.value))}
                  className="w-full mt-2"
                />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm">Allow web access</span>
                  <Switch checked={allowWeb} onCheckedChange={setAllowWeb} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Allow filesystem access</span>
                  <Switch checked={allowFs} onCheckedChange={setAllowFs} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Allow shell execution</span>
                  <Switch checked={allowExec} onCheckedChange={setAllowExec} />
                </div>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <Button onClick={handleSave} disabled={saving} className="bg-[#4361ee] hover:bg-[#3651d4] gap-2">
              <Save className="w-4 h-4" /> {saving ? 'Saving...' : 'Save Agent'}
            </Button>
            <Button variant="outline" onClick={resetForm} className="border-[#334155] gap-2">
              <RotateCcw className="w-4 h-4" /> Reset Form
            </Button>
          </div>

          {currentAgent && (
            <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-sm text-green-400">
              Active agent: <strong>{currentAgent.name}</strong> ({currentAgent.agentId}) — {currentAgent.capabilities.length} capabilities
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
