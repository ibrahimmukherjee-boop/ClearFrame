import { Shield, Fingerprint, Database, Eye, Crosshair, Radar, Workflow, BarChart3, Bot, Menu, Scale, Key, GitBranch, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { useSandbox } from '@/lib/sandbox-store'
import type { AuthUser } from '@/lib/auth-store'
import type { Section } from '../App'

interface HeaderProps {
  activeSection: Section
  setActiveSection: (s: Section) => void
  user?: AuthUser | null
  onLogout?: () => void
}

const navItems: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <Shield className="w-4 h-4" /> },
  { id: 'builder', label: 'Builder', icon: <Bot className="w-4 h-4" /> },
  { id: 'safepulse', label: 'SafePulse', icon: <Fingerprint className="w-4 h-4" /> },
  { id: 'trustregistry', label: 'TrustRegistry', icon: <Database className="w-4 h-4" /> },
  { id: 'clearframe', label: 'ClearFrame', icon: <Eye className="w-4 h-4" /> },
  { id: 'aegis', label: 'Aegis', icon: <Crosshair className="w-4 h-4" /> },
  { id: 'sonar', label: 'Sonar', icon: <Radar className="w-4 h-4" /> },
  { id: 'governance', label: 'Governance', icon: <Scale className="w-4 h-4" /> },
  { id: 'vault', label: 'Vault', icon: <Key className="w-4 h-4" /> },
  { id: 'workflows', label: 'Workflows', icon: <GitBranch className="w-4 h-4" /> },
  { id: 'pipeline', label: 'Pipeline', icon: <Workflow className="w-4 h-4" /> },
  { id: 'roi', label: 'Metrics', icon: <BarChart3 className="w-4 h-4" /> },
]

export function Header({ activeSection, setActiveSection, user, onLogout }: HeaderProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { backendOnline, loading } = useSandbox()

  return (
    <header className="sticky top-0 z-50 bg-[#0a0e1a]/95 backdrop-blur-md border-b border-[#1e293b]">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-[#4361ee] rotate-45 flex items-center justify-center">
            <span className="text-white font-bold text-xs -rotate-45">E</span>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white leading-tight">Erasys</h1>
            <p className="text-[10px] text-gray-400 leading-tight flex items-center gap-1.5">
              AI Governance and Safety
              {!loading && (
                <span className={`inline-block w-1.5 h-1.5 rounded-full ${backendOnline ? 'bg-green-400' : 'bg-red-400'}`} title={backendOnline ? 'API online' : 'API offline'} />
              )}
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" className="md:hidden" onClick={() => setMobileOpen(!mobileOpen)}>
          <Menu className="w-5 h-5" />
        </Button>
        <nav className="hidden md:flex items-center gap-1 overflow-x-auto">
          {navItems.map((item) => (
            <Button
              key={item.id}
              variant={activeSection === item.id ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setActiveSection(item.id)}
              className={`gap-1.5 text-xs shrink-0 ${
                activeSection === item.id
                  ? 'bg-[#4361ee] hover:bg-[#3651d4]'
                  : 'text-gray-400 hover:text-white hover:bg-[#1e293b]'
              }`}
            >
              {item.icon}
              {item.label}
            </Button>
          ))}
          {user && (
            <div className="flex items-center gap-2 ml-2 pl-2 border-l border-[#1e293b]">
              <span className="text-[10px] text-gray-500">{user.name} ({user.role})</span>
              <Button variant="ghost" size="sm" onClick={onLogout} className="text-gray-400 hover:text-white h-7 w-7 p-0">
                <LogOut className="w-3.5 h-3.5" />
              </Button>
            </div>
          )}
        </nav>
      </div>
      {mobileOpen && (
        <nav className="md:hidden border-t border-[#1e293b] px-2 py-2 grid grid-cols-3 gap-1">
          {navItems.map((item) => (
            <Button
              key={item.id}
              variant={activeSection === item.id ? 'default' : 'ghost'}
              size="sm"
              onClick={() => {
                setActiveSection(item.id)
                setMobileOpen(false)
              }}
              className={`gap-1 text-[10px] ${activeSection === item.id ? 'bg-[#4361ee]' : 'text-gray-400'}`}
            >
              {item.icon}
              {item.label}
            </Button>
          ))}
        </nav>
      )}
    </header>
  )
}
