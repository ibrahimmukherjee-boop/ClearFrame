import { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { BarChart3, TrendingDown, Shield, Clock, Users, Zap, Activity } from 'lucide-react'
import { useSandbox } from '@/lib/sandbox-store'
import type { RoiResult } from '@/lib/sandbox-types'

export function ROIDashboard() {
  const { calculateRoi } = useSandbox()
  const [data, setData] = useState<RoiResult | null>(null)

  useEffect(() => {
    calculateRoi(0, 0, 0).then(setData).catch(() => {})
  }, [calculateRoi])

  if (!data) return null

  const live = data.liveStats

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[#00d4aa] flex items-center justify-center">
          <BarChart3 className="w-5 h-5 text-[#0a0e1a]" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Platform Metrics</h2>
          <p className="text-sm text-gray-400">Live governance data from this deployment — updates as you run sessions</p>
        </div>
        <Badge className="ml-auto bg-green-500/20 text-green-400 border-green-500/30">Live</Badge>
      </div>

      {live && (
        <Card className="bg-[#0f172a] border-[#1e293b] mb-6">
          <CardContent className="p-6">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4 text-[#00d4aa]" />
              <h3 className="font-semibold text-sm">Current platform state</h3>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div><p className="text-gray-500">Registered agents</p><p className="text-xl font-bold">{live.registeredAgents}</p></div>
              <div><p className="text-gray-500">Verified operators</p><p className="text-xl font-bold">{live.verifiedOperators}</p></div>
              <div><p className="text-gray-500">Sessions run</p><p className="text-xl font-bold">{live.sessionsRun}</p></div>
              <div><p className="text-gray-500">Pending HITL</p><p className="text-xl font-bold text-amber-400">{live.pendingApprovals}</p></div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        {data.metrics.map((m) => (
          <Card key={m.label} className="bg-[#0f172a] border-[#1e293b]">
            <CardContent className="p-4">
              <div className="text-green-400 mb-2">
                {m.label.includes('Block') && <Shield className="w-5 h-5" />}
                {m.label.includes('HITL') && <Users className="w-5 h-5" />}
                {m.label.includes('Auth') && <Clock className="w-5 h-5" />}
                {m.label.includes('Alignment') && <TrendingDown className="w-5 h-5" />}
                {m.label.includes('Threat') && <Zap className="w-5 h-5" />}
              </div>
              <p className="text-2xl font-bold">
                {m.value}{m.unit}
              </p>
              <p className="text-xs text-gray-400">{m.label}</p>
              {m.description && (
                <p className="text-[10px] text-gray-500 mt-1">{m.description}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {data.activitySummary && data.activitySummary.length > 0 && (
        <Card className="bg-[#0f172a] border-[#1e293b]">
          <CardContent className="p-6">
            <h3 className="font-semibold mb-4">Activity summary</h3>
            <p className="text-xs text-gray-500 mb-4">
              Counts from the database on this instance. Run the pipeline or start a session to see numbers change.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {data.activitySummary.map((row) => (
                <div key={row.label} className="p-3 bg-[#1e293b]/50 rounded-lg">
                  <p className="text-xs text-gray-500">{row.label}</p>
                  <p className="text-lg font-bold">{row.value}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  )
}
