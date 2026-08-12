import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Shield, CheckCircle2, AlertTriangle, XCircle, RefreshCw, FileText, Scale, Building2,
  Truck, ScrollText, Brain, Hand, Check, Ban, ArrowUpCircle, Upload, Plus, ChevronRight,
} from 'lucide-react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'
import { api } from '@/lib/api'

interface GovernanceDashboardProps {
  compact?: boolean
}

type Framework = { frameworkId: string; name: string; label: string; attested: boolean; score: number; enabled: boolean }
type PolicyDoc = { docId: string; title: string; category: string; content: string; fileName?: string; version: string; enforced: boolean; cards?: PolicyCard[]; cardCount?: number }
type PolicyCard = { cardId: string; docId: string; title: string; content: string; priority: number; hierarchyOrder: number; parentCardId?: string; enforce: boolean }
type AgentAction = { actionId: string; tool: string; args: string; reasoning: string; alignment: number; status: string; hitlDecision?: string; time?: string; operatorNote?: string }

const statusIcon = { compliant: <CheckCircle2 className="w-4 h-4 text-green-400" />, attention: <AlertTriangle className="w-4 h-4 text-yellow-400" />, 'non-compliant': <XCircle className="w-4 h-4 text-red-400" /> }
const fwColors: Record<string, string> = { iso42001: 'purple', eu_ai_act: 'blue', gdpr: 'green' }

export function GovernanceDashboard({ compact }: GovernanceDashboardProps) {
  const { governance, toolCalls, collectEvidence, refresh, approveToolCall, blockToolCall } = useSandbox()
  const [hub, setHub] = useState<Record<string, unknown> | null>(null)
  const [actions, setActions] = useState<AgentAction[]>([])
  const [reasoning, setReasoning] = useState<Array<Record<string, unknown>>>([])
  const [collecting, setCollecting] = useState(false)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadContent, setUploadContent] = useState('')
  const [overrideNote, setOverrideNote] = useState('')
  const [selectedCall, setSelectedCall] = useState<string | null>(null)

  const [uploading, setUploading] = useState(false)

  const loadHub = useCallback(async () => {
    try {
      const data = await api.getGovernanceHub()
      setHub(data)
      const acts = await api.getAgentActions()
      setActions(acts as AgentAction[])
      const chain = await api.getReasoningChain()
      setReasoning(chain)
    } catch {
      /* hub loads on next refresh */
    }
  }, [])

  useEffect(() => { loadHub() }, [loadHub])

  const handleCollect = async () => {
    setCollecting(true)
    try {
      await collectEvidence()
      await loadHub()
      await refresh()
      toast.success('Evidence collected for all frameworks')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed')
    } finally {
      setCollecting(false)
    }
  }

  const handleAttest = async (fwId: string) => {
    try {
      await api.attestFramework(fwId, true, `Attested ${new Date().toLocaleDateString()}`)
      await loadHub()
      toast.success(`${fwId} attested`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Attest failed')
    }
  }

  const handleUpload = async (category: 'internal' | 'supplier') => {
    if (!uploadTitle.trim()) {
      toast.error('Policy title is required')
      return
    }
    if (!uploadContent.trim()) {
      toast.error('Policy content is required — paste text or upload a file')
      return
    }
    setUploading(true)
    try {
      const doc = await api.uploadPolicy({
        title: uploadTitle.trim(),
        category,
        content: uploadContent.trim(),
        fileName: `${uploadTitle.trim().replace(/\s+/g, '-')}.md`,
      })
      const cardCount = Array.isArray((doc as PolicyDoc).cards) ? (doc as PolicyDoc).cards!.length : 0
      setUploadTitle('')
      setUploadContent('')
      await loadHub()
      toast.success(cardCount ? `Policy uploaded — ${cardCount} enforceable rules parsed` : 'Policy uploaded')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleFileSelect = async (file: File | null) => {
    if (!file) return
    const text = await file.text()
    setUploadContent(text)
    if (!uploadTitle.trim()) {
      setUploadTitle(file.name.replace(/\.[^.]+$/, ''))
    }
    toast.info(`Loaded ${file.name}`)
  }

  const handleOverride = async (callId: string) => {
    if (!overrideNote.trim()) { toast.error('Override requires a justification note'); return }
    try {
      await api.overrideToolCall(callId, overrideNote)
      setOverrideNote('')
      setSelectedCall(null)
      await loadHub()
      await refresh()
      toast.success('Action overridden with justification')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Override failed')
    }
  }

  const frameworks = (hub?.frameworks as Framework[]) || []
  const externalLaw = (hub?.externalLaw as PolicyDoc[]) || []
  const internalPolicies = (hub?.internalPolicies as PolicyDoc[]) || []
  const supplierPolicies = (hub?.supplierPolicies as PolicyDoc[]) || []

  if (compact) {
    const avg = frameworks.length ? Math.round(frameworks.reduce((s, f) => s + f.score, 0) / frameworks.length) : governance?.complianceScore ?? 0
    return (
      <Card className="bg-[#0f172a] border-[#1e293b] hover:border-purple-500/50 transition-colors">
        <CardContent className="p-6 pt-6">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-purple-400" />
            <p className="text-sm font-semibold">Governance</p>
          </div>
          <p className="text-3xl font-bold">{avg}%</p>
          <p className="text-xs text-gray-400">ISO · EU AI Act · GDPR</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-purple-600 flex items-center justify-center">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Governance Hub</h2>
          <p className="text-sm text-gray-400">Regulatory frameworks · Policy hierarchy · Audit trail · Human-in-the-loop</p>
        </div>
        <Button onClick={handleCollect} disabled={collecting} className="ml-auto bg-purple-600 gap-2">
          <RefreshCw className={`w-4 h-4 ${collecting ? 'animate-spin' : ''}`} /> Collect Evidence
        </Button>
      </div>

      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 mb-6 text-sm text-amber-200/90">
        <p className="font-medium mb-1">Certification scope</p>
        <p className="text-xs text-amber-200/70">
          This hub generates technical evidence for ISO 42001, EU AI Act, and GDPR. Organizational artifacts — written policies, training records, supplier due diligence, and external auditor sign-off — must be maintained separately and uploaded here as internal or supplier policies.
        </p>
      </div>

      {/* Framework ticks */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {frameworks.map((fw) => (
          <Card key={fw.frameworkId} className={`bg-[#0f172a] border-[#1e293b] border-l-4 border-l-${fwColors[fw.frameworkId] || 'purple'}-500`}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {fw.attested ? <CheckCircle2 className="w-5 h-5 text-green-400" /> : <div className="w-5 h-5 rounded border-2 border-gray-500" />}
                  <span className="font-semibold">{fw.name}</span>
                </div>
                <Badge className="bg-purple-600/20 text-purple-300">{fw.score}%</Badge>
              </div>
              <p className="text-xs text-gray-500 mb-3">{fw.label}</p>
              <Button size="sm" variant="outline" className="w-full border-[#334155] text-xs" onClick={() => handleAttest(fw.frameworkId)} disabled={fw.attested}>
                {fw.attested ? 'Attested' : 'Attest Compliance'}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="external" className="space-y-4">
        <TabsList className="bg-[#1e293b] flex flex-wrap h-auto gap-1 p-1">
          <TabsTrigger value="external" className="gap-1.5 text-xs"><Scale className="w-3.5 h-3.5" /> External Law</TabsTrigger>
          <TabsTrigger value="internal" className="gap-1.5 text-xs"><Building2 className="w-3.5 h-3.5" /> Internal Policies</TabsTrigger>
          <TabsTrigger value="supplier" className="gap-1.5 text-xs"><Truck className="w-3.5 h-3.5" /> Supplier Policies</TabsTrigger>
          <TabsTrigger value="audit" className="gap-1.5 text-xs"><ScrollText className="w-3.5 h-3.5" /> Audit & HITL</TabsTrigger>
          <TabsTrigger value="controls" className="gap-1.5 text-xs"><Shield className="w-3.5 h-3.5" /> ISO Controls</TabsTrigger>
        </TabsList>

        {/* EXTERNAL LAW */}
        <TabsContent value="external">
          <p className="text-sm text-gray-400 mb-4">Reference regulatory frameworks — read-only. Broken into enforceable policy cards.</p>
          <div className="space-y-4">
            {externalLaw.map((doc) => (
              <Card key={doc.docId} className="bg-[#0f172a] border-[#1e293b]">
                <CardContent className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <Scale className="w-4 h-4 text-blue-400" />
                    <h3 className="font-semibold">{doc.title}</h3>
                    <Badge className="ml-auto bg-blue-500/20 text-blue-300 text-[10px]">External Law</Badge>
                  </div>
                  <p className="text-sm text-gray-400 mb-4">{doc.content?.slice(0, 200)}...</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {(doc.cards || []).map((card) => (
                      <div key={card.cardId} className="p-3 bg-[#1e293b]/60 rounded-lg border border-[#334155]">
                        <div className="flex items-center gap-2 mb-1">
                          <ChevronRight className="w-3 h-3 text-gray-500" />
                          <span className="text-sm font-medium">{card.title}</span>
                          {card.enforce && <Badge className="text-[9px] bg-green-500/20 text-green-400 ml-auto">Enforced</Badge>}
                        </div>
                        <p className="text-xs text-gray-500">{card.content}</p>
                        <p className="text-[10px] text-gray-600 mt-1">Priority {card.priority} · Order {card.hierarchyOrder}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* INTERNAL POLICIES */}
        <TabsContent value="internal">
          <Card className="bg-[#0f172a] border-[#1e293b] mb-4">
            <CardContent className="p-6 space-y-3">
              <h3 className="font-semibold flex items-center gap-2"><Upload className="w-4 h-4" /> Upload Internal Policy</h3>
              <Input placeholder="Policy title" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
              <div className="flex flex-wrap gap-2 items-center">
                <label className="cursor-pointer inline-flex items-center gap-2 px-3 py-2 rounded-md border border-[#334155] bg-[#1e293b] text-xs text-gray-300 hover:border-purple-500/50">
                  <Upload className="w-3.5 h-3.5" /> Upload .txt / .md file
                  <input type="file" accept=".txt,.md,.markdown,text/plain" className="hidden"
                    onChange={(e) => { void handleFileSelect(e.target.files?.[0] ?? null); e.target.value = '' }} />
                </label>
              </div>
              <textarea placeholder="Policy content (paste or type)..." value={uploadContent} onChange={(e) => setUploadContent(e.target.value)} rows={4}
                className="w-full px-3 py-2 bg-[#1e293b] border border-[#334155] rounded-md text-sm text-white" />
              <Button onClick={() => handleUpload('internal')} disabled={uploading} className="bg-purple-600 gap-2">
                <Plus className="w-4 h-4" /> {uploading ? 'Uploading...' : 'Upload Policy'}
              </Button>
            </CardContent>
          </Card>
          <PolicyDocList docs={internalPolicies} categoryLabel="Internal" color="purple" onUpdate={loadHub} />
        </TabsContent>

        {/* SUPPLIER POLICIES */}
        <TabsContent value="supplier">
          <Card className="bg-[#0f172a] border-[#1e293b] mb-4">
            <CardContent className="p-6 space-y-3">
              <h3 className="font-semibold flex items-center gap-2"><Truck className="w-4 h-4" /> Upload Supplier Policy</h3>
              <Input placeholder="Supplier policy title" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
              <div className="flex flex-wrap gap-2 items-center">
                <label className="cursor-pointer inline-flex items-center gap-2 px-3 py-2 rounded-md border border-[#334155] bg-[#1e293b] text-xs text-gray-300 hover:border-teal-500/50">
                  <Upload className="w-3.5 h-3.5" /> Upload .txt / .md file
                  <input type="file" accept=".txt,.md,.markdown,text/plain" className="hidden"
                    onChange={(e) => { void handleFileSelect(e.target.files?.[0] ?? null); e.target.value = '' }} />
                </label>
              </div>
              <textarea placeholder="Supplier policy requirements..." value={uploadContent} onChange={(e) => setUploadContent(e.target.value)} rows={4}
                className="w-full px-3 py-2 bg-[#1e293b] border border-[#334155] rounded-md text-sm text-white" />
              <Button onClick={() => handleUpload('supplier')} disabled={uploading} className="bg-teal-600 gap-2">
                <Plus className="w-4 h-4" /> {uploading ? 'Uploading...' : 'Upload Supplier Policy'}
              </Button>
            </CardContent>
          </Card>
          <PolicyDocList docs={supplierPolicies} categoryLabel="Supplier" color="teal" onUpdate={loadHub} />
        </TabsContent>

        {/* AUDIT & HITL */}
        <TabsContent value="audit">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="bg-[#0f172a] border-[#1e293b]">
              <CardContent className="p-6">
                <h3 className="font-semibold mb-4 flex items-center gap-2"><Brain className="w-4 h-4 text-cyan-400" /> Reasoning Chain</h3>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {reasoning.length === 0 && actions.length === 0 ? (
                    <p className="text-sm text-gray-500">Run a pipeline or agent session to see the reasoning chain.</p>
                  ) : (
                    (reasoning.length ? reasoning : actions).map((step, i) => (
                      <div key={i} className="p-3 bg-[#1e293b]/50 rounded-lg border-l-2 border-cyan-500/50">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs text-gray-500">Step {(step as {step?: number}).step ?? i + 1}</span>
                          <Badge className="text-[9px]">{String((step as AgentAction).tool || 'think')}</Badge>
                        </div>
                        <p className="text-sm text-gray-300">{String((step as AgentAction).reasoning || (step as {reasoning?: string}).reasoning || '—')}</p>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>

            <Card className="bg-[#0f172a] border-[#1e293b]">
              <CardContent className="p-6">
                <h3 className="font-semibold mb-4 flex items-center gap-2"><Hand className="w-4 h-4 text-orange-400" /> Human-in-the-Loop</h3>
                <p className="text-xs text-gray-500 mb-4">Approve, block, or override agent actions. Overrides require written justification.</p>
                <div className="space-y-3 max-h-80 overflow-y-auto">
                  {toolCalls.map((call) => (
                    <div key={call.id} className="p-3 bg-[#1e293b]/50 rounded-lg">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium">{call.tool}</span>
                        <Badge className={`text-[9px] ml-auto ${call.status === 'allowed' ? 'bg-green-500/20 text-green-400' : call.status === 'blocked' ? 'bg-red-500/20 text-red-400' : call.status === 'overridden' ? 'bg-blue-500/20 text-blue-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                          {call.status}
                        </Badge>
                      </div>
                      <p className="text-xs text-gray-500 truncate">{call.args}</p>
                      {call.reasoning && <p className="text-xs text-cyan-400/70 mt-1 italic">"{call.reasoning.slice(0, 80)}..."</p>}
                      {(call.status === 'human_review' || call.status === 'pending') && (
                        <div className="flex gap-1 mt-2">
                          <Button size="sm" className="h-7 bg-green-600 px-2" onClick={() => { approveToolCall(call.id); loadHub() }}><Check className="w-3 h-3" /></Button>
                          <Button size="sm" className="h-7 bg-red-600 px-2" onClick={() => { blockToolCall(call.id); loadHub() }}><Ban className="w-3 h-3" /></Button>
                          <Button size="sm" variant="outline" className="h-7 border-blue-500/50 text-blue-400 px-2" onClick={() => setSelectedCall(call.id)}><ArrowUpCircle className="w-3 h-3" /></Button>
                        </div>
                      )}
                      {selectedCall === call.id && (
                        <div className="mt-2 flex gap-2">
                          <Input placeholder="Override justification (required)" value={overrideNote} onChange={(e) => setOverrideNote(e.target.value)} className="h-7 text-xs bg-[#1e293b]" />
                          <Button size="sm" className="h-7 bg-blue-600" onClick={() => handleOverride(call.id)}>Override</Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="bg-[#0f172a] border-[#1e293b] mt-4">
            <CardContent className="p-6">
              <h3 className="font-semibold mb-4">Full Action Audit Log</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-gray-500 text-left border-b border-[#334155]">
                    <th className="pb-2 pr-4">Time</th><th className="pb-2 pr-4">Agent</th><th className="pb-2 pr-4">Tool</th><th className="pb-2 pr-4">Reasoning</th><th className="pb-2 pr-4">Align</th><th className="pb-2">HITL</th>
                  </tr></thead>
                  <tbody>
                    {actions.map((a) => (
                      <tr key={a.actionId} className="border-b border-[#1e293b]">
                        <td className="py-2 pr-4 text-gray-500 font-mono text-xs">{a.time}</td>
                        <td className="py-2 pr-4 text-xs">{a.tool}</td>
                        <td className="py-2 pr-4 text-xs truncate max-w-[120px]">{a.args?.slice(0, 40)}</td>
                        <td className="py-2 pr-4 text-xs text-cyan-400/80 max-w-[200px] truncate">{a.reasoning || '—'}</td>
                        <td className="py-2 pr-4 text-xs">{a.alignment}%</td>
                        <td className="py-2 text-xs">{a.hitlDecision || a.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ISO CONTROLS */}
        <TabsContent value="controls">
          {governance && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {governance.controls.map((ctrl) => (
                <div key={ctrl.id} className="flex items-center gap-3 p-3 rounded bg-[#1e293b]/50">
                  {statusIcon[ctrl.status as keyof typeof statusIcon]}
                  <div className="flex-1"><p className="text-sm font-medium">{ctrl.id} — {ctrl.title}</p><p className="text-xs text-gray-500">{ctrl.clause}</p></div>
                  <Badge className="text-[10px]">{ctrl.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </section>
  )
}

function PolicyDocList({ docs, categoryLabel, color, onUpdate }: { docs: PolicyDoc[]; categoryLabel: string; color: string; onUpdate?: () => void }) {
  const toggleEnforce = async (card: PolicyCard) => {
    try {
      await api.updateCardHierarchy(card.cardId, card.parentCardId ?? null, card.hierarchyOrder, !card.enforce)
      onUpdate?.()
      toast.success(card.enforce ? 'Enforcement disabled' : 'Enforcement enabled')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Update failed')
    }
  }

  const moveCard = async (card: PolicyCard, direction: -1 | 1) => {
    const nextOrder = Math.max(0, card.hierarchyOrder + direction)
    try {
      await api.updateCardHierarchy(card.cardId, card.parentCardId ?? null, nextOrder, card.enforce)
      onUpdate?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Reorder failed')
    }
  }

  if (!docs.length) return <p className="text-sm text-gray-500">No {categoryLabel.toLowerCase()} policies uploaded yet.</p>
  return (
    <div className="space-y-4">
      {docs.map((doc) => (
        <Card key={doc.docId} className="bg-[#0f172a] border-[#1e293b]">
          <CardContent className="p-6">
            <div className="flex items-center gap-2 mb-2">
              <FileText className={`w-4 h-4 text-${color}-400`} />
              <h3 className="font-semibold">{doc.title}</h3>
              <Badge className="ml-auto text-[10px]">v{doc.version}</Badge>
            </div>
            <p className="text-sm text-gray-400 mb-3">{doc.content?.slice(0, 150)}...</p>
            {(doc.cards || []).length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {doc.cards!.map((card) => (
                  <div key={card.cardId} className="p-3 bg-[#1e293b]/50 rounded border border-[#334155]">
                    <p className="text-sm font-medium">{card.title}</p>
                    <p className="text-xs text-gray-500 mt-1">{card.content}</p>
                    <div className="flex gap-2 mt-2 items-center flex-wrap">
                      <Badge className="text-[9px]">P{card.priority}</Badge>
                      <Badge className="text-[9px]">Order {card.hierarchyOrder}</Badge>
                      {card.enforce ? (
                        <Badge className="text-[9px] bg-green-500/20 text-green-400">Enforced</Badge>
                      ) : (
                        <Badge className="text-[9px] bg-gray-500/20 text-gray-400">Advisory</Badge>
                      )}
                      {onUpdate && (
                        <>
                          <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 border-[#334155]" onClick={() => moveCard(card, -1)}>↑</Button>
                          <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 border-[#334155]" onClick={() => moveCard(card, 1)}>↓</Button>
                          <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 border-[#334155]" onClick={() => toggleEnforce(card)}>
                            {card.enforce ? 'Disable' : 'Enforce'}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
