import { useEffect, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Scale, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'

interface Assessment {
  agentId: string
  agentName: string
  riskCategory: string
  conformityScore: number
  obligations: string[]
  gaps: string[]
  compliant: boolean
}

export function EuAiActDashboard() {
  const [data, setData] = useState<{
    totalAgents: number
    highRiskAgents: number
    compliantAgents: number
    portfolioScore: number
    assessments: Assessment[]
  } | null>(null)

  useEffect(() => {
    api.getEuAiAct().then((d) => setData(d as typeof data)).catch(() => {})
  }, [])

  if (!data) return <p className="text-center text-gray-400 py-12">Loading EU AI Act assessment...</p>

  const catColor: Record<string, string> = {
    high_risk: 'bg-red-500/20 text-red-400',
    limited_risk: 'bg-yellow-500/20 text-yellow-400',
    minimal_risk: 'bg-green-500/20 text-green-400',
  }

  return (
    <section className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-blue-700 flex items-center justify-center">
          <Scale className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">EU AI Act Conformity</h2>
          <p className="text-sm text-gray-400">Risk classification and conformity assessment per agent</p>
        </div>
        <Badge className="ml-auto bg-blue-700/20 text-blue-400">{data.portfolioScore}% Portfolio Score</Badge>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <Card className="bg-[#0f172a] border-[#1e293b]"><CardContent className="p-4"><p className="text-xs text-gray-400">Total Agents</p><p className="text-2xl font-bold">{data.totalAgents}</p></CardContent></Card>
        <Card className="bg-[#0f172a] border-[#1e293b]"><CardContent className="p-4"><p className="text-xs text-gray-400">High Risk</p><p className="text-2xl font-bold text-red-400">{data.highRiskAgents}</p></CardContent></Card>
        <Card className="bg-[#0f172a] border-[#1e293b]"><CardContent className="p-4"><p className="text-xs text-gray-400">Compliant</p><p className="text-2xl font-bold text-green-400">{data.compliantAgents}</p></CardContent></Card>
      </div>

      <div className="space-y-4">
        {data.assessments.map((a) => (
          <Card key={a.agentId} className="bg-[#0f172a] border-[#1e293b]">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                {a.compliant ? <CheckCircle2 className="w-5 h-5 text-green-400" /> : <AlertTriangle className="w-5 h-5 text-yellow-400" />}
                <h3 className="font-semibold">{a.agentName}</h3>
                <Badge className={catColor[a.riskCategory] || ''}>{a.riskCategory.replace('_', ' ')}</Badge>
                <span className="ml-auto text-sm text-gray-400">Score: {a.conformityScore}</span>
              </div>
              {a.obligations.length > 0 && (
                <div className="mb-2">
                  <p className="text-xs text-gray-500 mb-1">Obligations:</p>
                  <ul className="text-sm text-gray-400 list-disc list-inside">{a.obligations.map((o) => <li key={o}>{o}</li>)}</ul>
                </div>
              )}
              {a.gaps.length > 0 && (
                <div>
                  <p className="text-xs text-red-400 mb-1">Gaps:</p>
                  <ul className="text-sm text-red-300 list-disc list-inside">{a.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}
