import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ArrowRight, Shield, Fingerprint, Database, Eye, Crosshair, Radar, Bot } from 'lucide-react'
import type { Section } from '../App'

interface HeroSectionProps {
  setActiveSection: (s: Section) => void
}

const stackItems = [
  { label: 'Agent Builder', section: 'builder' as Section, icon: <Bot className="w-4 h-4" />, color: 'bg-[#4361ee]', desc: 'BUILD your agent' },
  { label: 'SafePulse', section: 'safepulse' as Section, icon: <Fingerprint className="w-4 h-4" />, color: 'bg-blue-500', desc: 'WHO is the operator?' },
  { label: 'TrustRegistry', section: 'trustregistry' as Section, icon: <Database className="w-4 h-4" />, color: 'bg-purple-500', desc: 'IS the agent trusted?' },
  { label: 'ClearFrame', section: 'clearframe' as Section, icon: <Eye className="w-4 h-4" />, color: 'bg-green-500', desc: 'WHAT is the agent doing?' },
  { label: 'Aegis', section: 'aegis' as Section, icon: <Crosshair className="w-4 h-4" />, color: 'bg-orange-500', desc: 'SHOULD the agent do this?' },
  { label: 'Sonar', section: 'sonar' as Section, icon: <Radar className="w-4 h-4" />, color: 'bg-red-500', desc: 'Real-time threat detection' },
]

export function HeroSection({ setActiveSection }: HeroSectionProps) {
  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-[#4361ee]/10 via-transparent to-[#00d4aa]/5" />
      <div className="max-w-7xl mx-auto px-6 py-16 relative">
        <div className="flex flex-col lg:flex-row items-center gap-12">
          <div className="flex-1 text-center lg:text-left">
            <Badge className="bg-[#4361ee]/20 text-[#4361ee] border-[#4361ee]/30 mb-4">
              <Shield className="w-3 h-3 mr-1" /> Interactive PoC Sandbox
            </Badge>
            <h2 className="text-4xl lg:text-5xl font-bold mb-4 leading-tight">
              Erasys <span className="text-[#4361ee]">AI Governance and Safety</span>
            </h2>
            <p className="text-gray-400 text-lg mb-6 max-w-xl">
              Build agents, upload governance policies, and run them through the full trust pipeline — live.
              Policy enforcement, human-in-the-loop approval, and tamper-evident audit in one control plane.
            </p>
            <div className="flex flex-wrap gap-3 justify-center lg:justify-start">
              <Button onClick={() => setActiveSection('builder')} className="bg-[#4361ee] hover:bg-[#3651d4] gap-2">
                Build an Agent <ArrowRight className="w-4 h-4" />
              </Button>
              <Button onClick={() => setActiveSection('safepulse')} variant="outline" className="border-[#1e293b] hover:bg-[#1e293b] gap-2">
                Explore SafePulse <ArrowRight className="w-4 h-4" />
              </Button>
              <Button
                variant="outline"
                onClick={() => setActiveSection('pipeline')}
                className="border-[#1e293b] hover:bg-[#1e293b] gap-2"
              >
                Run Full Pipeline <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
          <div className="flex-1 w-full max-w-md">
            <div className="bg-[#0f172a] rounded-xl border border-[#1e293b] p-6 space-y-3">
              <h3 className="text-sm font-semibold text-gray-400 mb-4 uppercase tracking-wider">The Five Layers</h3>
              {stackItems.map((item, i) => (
                <div
                  key={item.label}
                  className="flex items-center gap-3 p-3 rounded-lg bg-[#1e293b]/50 hover:bg-[#1e293b] transition-colors cursor-pointer group"
                  onClick={() => setActiveSection(item.section)}
                >
                  <div className={`w-8 h-8 rounded-lg ${item.color} flex items-center justify-center text-white`}>
                    {item.icon}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-sm">{item.label}</p>
                    <p className="text-xs text-gray-500">{item.desc}</p>
                  </div>
                  <span className="text-xs text-gray-600 font-mono">0{i + 1}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
