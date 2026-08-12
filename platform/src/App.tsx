import { SandboxProvider, useSandbox } from '@/lib/sandbox-store'
import { AuthProvider, useAuth } from '@/lib/auth-store'
import { LoginPage } from './sections/LoginPage'
import { Header } from './sections/Header'
import { HeroSection } from './sections/HeroSection'
import { AgentBuilderDemo } from './sections/AgentBuilderDemo'
import { SafePulseDemo } from './sections/SafePulseDemo'
import { TrustRegistryDemo } from './sections/TrustRegistryDemo'
import { ClearFrameDemo } from './sections/ClearFrameDemo'
import { AegisDemo } from './sections/AegisDemo'
import { SonarDemo } from './sections/SonarDemo'
import { FullPipelineDemo } from './sections/FullPipelineDemo'
import { ROIDashboard } from './sections/ROIDashboard'
import { GovernanceDashboard } from './sections/GovernanceDashboard'
import { AgentManagement } from './sections/AgentManagement'
import { VaultManagement } from './sections/VaultManagement'
import { WorkflowBuilder } from './sections/WorkflowBuilder'
import { Footer } from './sections/Footer'
import { Toaster } from '@/components/ui/sonner'
import { useState } from 'react'

export type Section =
  | 'overview'
  | 'builder'
  | 'safepulse'
  | 'trustregistry'
  | 'clearframe'
  | 'aegis'
  | 'sonar'
  | 'pipeline'
  | 'governance'
  | 'vault'
  | 'euaiact'
  | 'workflows'
  | 'roi'

function AppContent() {
  const [activeSection, setActiveSection] = useState<Section>('overview')
  const { backendOnline, loading } = useSandbox()
  const { isAuthenticated, loading: authLoading, user, logout } = useAuth()

  if (authLoading) {
    return <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center text-gray-400">Loading...</div>
  }
  if (!isAuthenticated) {
    return <LoginPage />
  }

  const goTo = (section: Section) => setActiveSection(section)

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white font-sans">
      {!loading && !backendOnline && (
        <div className="bg-red-500/20 border-b border-red-500/30 text-red-300 text-sm text-center py-2 px-4">
          Backend offline — start the API with <code className="font-mono">npm run dev:all</code> or <code className="font-mono">./start-local.sh</code>
        </div>
      )}
      <Header activeSection={activeSection} setActiveSection={setActiveSection} user={user} onLogout={logout} />
      <main>
        {activeSection === 'overview' && (
          <>
            <HeroSection setActiveSection={setActiveSection} />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 p-6 max-w-7xl mx-auto">
              <div onClick={() => goTo('builder')} className="cursor-pointer">
                <AgentBuilderDemo compact />
              </div>
              <div onClick={() => goTo('safepulse')} className="cursor-pointer">
                <SafePulseDemo compact />
              </div>
              <div onClick={() => goTo('trustregistry')} className="cursor-pointer">
                <TrustRegistryDemo compact />
              </div>
              <div onClick={() => goTo('aegis')} className="cursor-pointer">
                <AegisDemo compact />
              </div>
              <div onClick={() => goTo('governance')} className="cursor-pointer">
                <GovernanceDashboard compact />
              </div>
            </div>
            <FullPipelineDemo />
            <ROIDashboard />
          </>
        )}
        {activeSection === 'builder' && (
          <>
            <AgentBuilderDemo />
            <AgentManagement />
          </>
        )}
        {activeSection === 'safepulse' && <SafePulseDemo />}
        {activeSection === 'trustregistry' && <TrustRegistryDemo />}
        {activeSection === 'clearframe' && <ClearFrameDemo />}
        {activeSection === 'aegis' && <AegisDemo />}
        {activeSection === 'sonar' && <SonarDemo />}
        {activeSection === 'pipeline' && <FullPipelineDemo />}
        {activeSection === 'governance' && <GovernanceDashboard />}
        {activeSection === 'euaiact' && <GovernanceDashboard />}
        {activeSection === 'vault' && <VaultManagement />}
        {activeSection === 'workflows' && <WorkflowBuilder />}
        {activeSection === 'roi' && <ROIDashboard />}
      </main>
      <Footer />
      <Toaster />
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <SandboxProvider>
        <AppContent />
      </SandboxProvider>
    </AuthProvider>
  )
}

export default App
