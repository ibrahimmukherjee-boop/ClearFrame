import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'
import { AGENT_PRESETS, ALL_CAPABILITIES, type AgentConfig, type ApiState, type CertTrustLevel, type GovernanceDashboard, type PipelineStepState, type RoiResult, type ToolCatalogEntry, type ToolConnection } from './sandbox-types'

interface SandboxContextValue extends Omit<ApiState, 'presets'> {
  loading: boolean
  backendOnline: boolean
  refresh: () => Promise<void>
  saveAgent: (input: Omit<AgentConfig, 'agentId' | 'trustScore' | 'status' | 'registeredAt' | 'owner' | 'isCurrent'>) => Promise<AgentConfig>
  loadPreset: (presetName: string) => Omit<AgentConfig, 'agentId' | 'trustScore' | 'status' | 'registeredAt' | 'owner' | 'isCurrent'> | null
  selectAgent: (agentId: string) => Promise<void>
  registerAgentInRegistry: (name: string, role: string) => Promise<AgentConfig>
  revokeAgent: (agentId: string) => Promise<void>
  suspendAgent: (agentId: string) => Promise<void>
  activateAgent: (agentId: string) => Promise<void>
  enrollSafepulse: (profile: number[]) => Promise<void>
  verifySafepulse: (profile: number[]) => Promise<{ success: boolean; score: number }>
  resetSafepulse: () => Promise<void>
  issueCertificate: (trustLevel: CertTrustLevel, ttlHours: number) => Promise<{ ok: boolean; message: string }>
  verifyCertificate: () => Promise<{ ok: boolean; message: string }>
  revokeCertificate: () => Promise<{ ok: boolean; message: string }>
  startAgentSession: () => Promise<{ ok: boolean; message: string }>
  approveToolCall: (callId: string) => Promise<void>
  blockToolCall: (callId: string) => Promise<void>
  overrideToolCall: (callId: string, note: string) => Promise<void>
  resetToolCalls: () => Promise<void>
  runFullPipeline: (onStepUpdate: (steps: PipelineStepState[]) => void, onComplete: (success: boolean) => void) => () => void
  resetSandbox: () => Promise<void>
  calculateRoi: (agents: number, operators: number, reductionPct: number) => Promise<RoiResult>
  createConnection: (toolId: string, name: string, config?: Record<string, unknown>) => Promise<ToolConnection>
  executeTool: (tool: string, args: Record<string, unknown>) => Promise<Record<string, unknown>>
  collectEvidence: () => Promise<{ collected: number }>
  safepulseEnrolled: boolean
  allCapabilities: readonly string[]
  presets: typeof AGENT_PRESETS
  toolCatalog: ToolCatalogEntry[]
  toolConnections: ToolConnection[]
  governance: GovernanceDashboard | undefined
}

const emptyState: ApiState = {
  currentAgent: null,
  agents: [],
  operator: null,
  cert: null,
  session: null,
  auditLog: [],
  toolCalls: [],
  threatEvents: [],
  threatScore: 42,
  pipelineLog: [],
  auditVerify: { valid: true, count: 0, message: '' },
  vaultKeys: [],
  presets: [],
  safepulseEnrolled: false,
}

const SandboxContext = createContext<SandboxContextValue | null>(null)

const STEP_META: PipelineStepState[] = [
  { id: 'builder', name: 'Agent Builder', status: 'pending', description: 'Defining agent configuration...' },
  { id: 'safepulse', name: 'SafePulse', status: 'pending', description: 'Authenticating operator...' },
  { id: 'trustregistry', name: 'TrustRegistry', status: 'pending', description: 'Issuing trust certificate...' },
  { id: 'clearframe', name: 'ClearFrame', status: 'pending', description: 'Initializing runtime sandbox...' },
  { id: 'aegis', name: 'Aegis', status: 'pending', description: 'Loading Goal Manifest...' },
  { id: 'sonar', name: 'Sonar', status: 'pending', description: 'Starting threat monitoring...' },
]

export function SandboxProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ApiState>(emptyState)
  const [loading, setLoading] = useState(true)
  const [backendOnline, setBackendOnline] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const data = await api.getState()
      setState(data)
      setBackendOnline(true)
    } catch {
      setBackendOnline(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 5000)
    return () => clearInterval(interval)
  }, [refresh])

  const saveAgent = useCallback(
    async (input: Omit<AgentConfig, 'agentId' | 'trustScore' | 'status' | 'registeredAt' | 'owner' | 'isCurrent'>) => {
      const agent = await api.saveAgent(input)
      await refresh()
      return agent
    },
    [refresh],
  )

  const loadPreset = useCallback((presetName: string) => AGENT_PRESETS[presetName] ?? null, [])

  const selectAgent = useCallback(
    async (agentId: string) => {
      await api.selectAgent(agentId)
      await refresh()
    },
    [refresh],
  )

  const registerAgentInRegistry = useCallback(
    async (name: string, role: string) => {
      const caps =
        role === 'code-review'
          ? ['file_read', 'git_read']
          : role === 'data-analysis'
            ? ['database_read']
            : role === 'customer-support'
              ? ['web_search', 'email_send']
              : role === 'security-scan'
                ? ['file_read', 'web_search']
                : ['shell_exec', 'webhook_send']
      return saveAgent({
        name,
        description: `Registered agent for ${role}`,
        capabilities: caps,
        provider: 'ollama',
        model: 'llama3',
        maxSteps: 10,
        allowWeb: role !== 'data-analysis',
        allowFs: role !== 'customer-support',
        allowExec: role === 'devops',
      })
    },
    [saveAgent],
  )

  const revokeAgent = useCallback(
    async (agentId: string) => {
      await api.revokeAgent(agentId)
      await refresh()
    },
    [refresh],
  )

  const suspendAgent = useCallback(
    async (agentId: string) => {
      await api.suspendAgent(agentId)
      await refresh()
    },
    [refresh],
  )

  const activateAgent = useCallback(
    async (agentId: string) => {
      await api.activateAgent(agentId)
      await refresh()
    },
    [refresh],
  )

  const createConnection = useCallback(
    async (toolId: string, name: string, config?: Record<string, unknown>) => {
      const conn = await api.createConnection(toolId, name, config)
      await refresh()
      return conn
    },
    [refresh],
  )

  const executeTool = useCallback((tool: string, args: Record<string, unknown>) => {
    return api.executeTool(tool, args)
  }, [])

  const collectEvidence = useCallback(async () => {
    const result = await api.collectEvidence()
    await refresh()
    return result
  }, [refresh])

  const enrollSafepulse = useCallback(
    async (profile: number[]) => {
      await api.enrollSafepulse(profile)
      await refresh()
    },
    [refresh],
  )

  const verifySafepulse = useCallback(
    async (profile: number[]) => {
      const result = await api.verifySafepulse(profile)
      await refresh()
      return result
    },
    [refresh],
  )

  const resetSafepulse = useCallback(async () => {
    await api.resetSafepulse()
    await refresh()
  }, [refresh])

  const issueCertificate = useCallback(
    async (trustLevel: CertTrustLevel, ttlHours: number) => {
      const result = await api.issueCertificate(trustLevel, ttlHours)
      await refresh()
      return { ok: result.ok, message: result.message }
    },
    [refresh],
  )

  const verifyCertificate = useCallback(async () => {
    const result = await api.verifyCertificate()
    return result
  }, [])

  const revokeCertificate = useCallback(async () => {
    const result = await api.revokeCertificate()
    await refresh()
    return result
  }, [refresh])

  const startAgentSession = useCallback(async () => {
    const result = await api.startSession()
    await refresh()
    return { ok: result.ok, message: result.message }
  }, [refresh])

  const approveToolCall = useCallback(
    async (callId: string) => {
      await api.approveToolCall(callId)
      await refresh()
    },
    [refresh],
  )

  const blockToolCall = useCallback(
    async (callId: string) => {
      await api.blockToolCall(callId)
      await refresh()
    },
    [refresh],
  )

  const overrideToolCall = useCallback(
    async (callId: string, note: string) => {
      await api.overrideToolCall(callId, note)
      await refresh()
    },
    [refresh],
  )

  const resetToolCalls = useCallback(async () => {
    await api.resetToolCalls()
    await refresh()
  }, [refresh])

  const runFullPipeline = useCallback(
    (onStepUpdate: (steps: PipelineStepState[]) => void, onComplete: (success: boolean) => void) => {
      let cancelled = false
      let index = 0

      const tick = () => {
        if (cancelled) return
        onStepUpdate(
          STEP_META.map((s, i) => ({
            ...s,
            status: i < index ? 'complete' : i === index ? 'running' : 'pending',
          })),
        )
      }

      tick()
      const interval = setInterval(() => {
        index++
        if (index < STEP_META.length) tick()
      }, 1200)

      api
        .runPipeline()
        .then(async (result) => {
          clearInterval(interval)
          if (cancelled) return
          onStepUpdate(STEP_META.map((s) => ({ ...s, status: result.ok ? 'complete' : 'failed' })))
          await refresh()
          onComplete(result.ok)
        })
        .catch(() => {
          clearInterval(interval)
          if (!cancelled) onComplete(false)
        })

      return () => {
        cancelled = true
        clearInterval(interval)
      }
    },
    [refresh],
  )

  const resetSandbox = useCallback(async () => {
    await api.resetSandbox()
    await refresh()
  }, [refresh])

  const calculateRoi = useCallback((agents: number, operators: number, reductionPct: number) => {
    return api.calculateRoi(agents, operators, reductionPct)
  }, [])

  const value = useMemo<SandboxContextValue>(
    () => ({
      ...state,
      loading,
      backendOnline,
      refresh,
      saveAgent,
      loadPreset,
      selectAgent,
      registerAgentInRegistry,
      revokeAgent,
      suspendAgent,
      activateAgent,
      enrollSafepulse,
      verifySafepulse,
      resetSafepulse,
      issueCertificate,
      verifyCertificate,
      revokeCertificate,
      startAgentSession,
      approveToolCall,
      blockToolCall,
      overrideToolCall,
      resetToolCalls,
      runFullPipeline,
      resetSandbox,
      calculateRoi,
      createConnection,
      executeTool,
      collectEvidence,
      safepulseEnrolled: state.safepulseEnrolled,
      allCapabilities: ALL_CAPABILITIES,
      presets: AGENT_PRESETS,
      toolCatalog: state.toolCatalog ?? [],
      toolConnections: state.toolConnections ?? [],
      governance: state.governance,
    }),
    [
      state,
      loading,
      backendOnline,
      refresh,
      saveAgent,
      loadPreset,
      selectAgent,
      registerAgentInRegistry,
      revokeAgent,
      suspendAgent,
      activateAgent,
      enrollSafepulse,
      verifySafepulse,
      resetSafepulse,
      issueCertificate,
      verifyCertificate,
      revokeCertificate,
      startAgentSession,
      approveToolCall,
      blockToolCall,
      overrideToolCall,
      resetToolCalls,
      runFullPipeline,
      resetSandbox,
      calculateRoi,
      createConnection,
      executeTool,
      collectEvidence,
    ],
  )

  return <SandboxContext.Provider value={value}>{children}</SandboxContext.Provider>
}

export function useSandbox() {
  const ctx = useContext(SandboxContext)
  if (!ctx) throw new Error('useSandbox must be used within SandboxProvider')
  return ctx
}
