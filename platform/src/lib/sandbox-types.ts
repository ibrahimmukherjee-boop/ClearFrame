export type AgentStatus = 'active' | 'suspended' | 'revoked'
export type CertTrustLevel = 'SANDBOX' | 'RESTRICTED' | 'STANDARD' | 'ELEVATED' | 'CRITICAL'
export type ToolCallStatus = 'pending' | 'pending_approval' | 'allowed' | 'blocked' | 'human_review' | 'overridden'
export type AuditStatus = 'allowed' | 'blocked' | 'flagged'
export type SessionStatus = 'pending' | 'approved' | 'running' | 'terminated' | 'denied'
export type ThreatSeverity = 'low' | 'medium' | 'high' | 'critical'
export type ThreatType = 'anomaly' | 'policy_violation' | 'credential_abuse' | 'insider_threat' | 'drift'

export interface AgentConfig {
  agentId: string
  name: string
  description: string
  capabilities: string[]
  provider: string
  model: string
  maxSteps: number
  allowWeb: boolean
  allowFs: boolean
  allowExec: boolean
  trustScore: number
  status: AgentStatus
  registeredAt: string
  owner: string
  isCurrent?: boolean
}

export interface OperatorSession {
  operatorId: string
  name: string
  verified: boolean
  trustScore: number
  authMethod: string
  timestamp: number
}

export interface TrustCert {
  certId: string
  agentId: string
  trustLevel: CertTrustLevel
  capabilities: string[]
  issuedAt: number
  expiresAt: number
  revoked: boolean
  signature: string
}

export interface AuditEntry {
  id: string
  timestamp: string
  action: string
  tool: string
  alignment: number
  status: AuditStatus
}

export interface ToolCall {
  id: string
  tool: string
  args: string
  alignment: number
  status: ToolCallStatus
  sessionId?: string
  reasoning?: string
}

export interface ThreatEvent {
  id: string
  timestamp: string
  agent: string
  type: ThreatType
  severity: ThreatSeverity
  description: string
}

export interface AgentSession {
  sessionId: string
  agentId: string
  status: SessionStatus
  startedAt: number
  endedAt?: number
}

export interface PipelineStepState {
  id: string
  name: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  description: string
  error?: string
}

export interface ApiState {
  currentAgent: AgentConfig | null
  agents: AgentConfig[]
  operator: OperatorSession | null
  cert: TrustCert | null
  session: AgentSession | null
  auditLog: AuditEntry[]
  toolCalls: ToolCall[]
  threatEvents: ThreatEvent[]
  threatScore: number
  pipelineLog: string[]
  auditVerify: { valid: boolean; count: number; message: string }
  vaultKeys: { key: string; masked: string }[]
  presets: string[]
  safepulseEnrolled: boolean
  toolCatalog?: ToolCatalogEntry[]
  toolConnections?: ToolConnection[]
  governance?: GovernanceDashboard
}

export interface ToolCatalogEntry {
  id: string
  name: string
  category: string
  icon: string
  requiresKey: boolean
  description: string
}

export interface ToolConnection {
  connectionId: string
  toolId: string
  name: string
  status: string
}

export interface GovernanceDashboard {
  controls: Array<{ id: string; clause: string; title: string; category: string; status: string }>
  complianceScore: number
  agents: { total: number; active: number; suspended: number }
  risks: Array<{ risk_id: string; title: string; tier: string }>
  policies: Array<{ policyId: string; title: string; version: string }>
  kpis: {
    auditIntegrity: boolean
    auditEntries: number
    threatScore: number
    activeThreats: number
    hitlPending: number
    operatorVerified: boolean
  }
}

export interface RoiResult {
  metrics: Array<{ label: string; value: number; target: number; unit: string; lowerIsBetter?: boolean; description?: string }>
  liveStats?: {
    registeredAgents: number
    verifiedOperators: number
    sessionsRun: number
    pendingApprovals: number
    toolCallsTotal: number
    toolCallsBlocked: number
    threatEvents: number
  }
  activitySummary?: Array<{ label: string; value: number }>
  dataSource?: string
}

export interface SandboxState {
  currentAgent: AgentConfig | null
  agents: AgentConfig[]
  operator: OperatorSession | null
  cert: TrustCert | null
  session: AgentSession | null
  auditLog: AuditEntry[]
  toolCalls: ToolCall[]
  threatEvents: ThreatEvent[]
  pipelineLog: string[]
  threatScore: number
  safepulseProfile: number[]
  safepulseEnrolled: boolean
}

export const ALL_CAPABILITIES = [
  'web_search',
  'web_fetch',
  'database_read',
  'file_read',
  'file_write',
  'email_send',
  'chart_generate',
  'pdf_read',
  'git_read',
  'git_write',
  'shell_exec',
  'webhook_send',
  'github',
  'slack',
  'api_call',
] as const

export const AGENT_PRESETS: Record<
  string,
  Omit<AgentConfig, 'agentId' | 'trustScore' | 'status' | 'registeredAt' | 'owner'>
> = {
  'Customer Support Bot': {
    name: 'Customer Support Bot',
    description: 'Handles customer queries, checks order status, escalates complaints.',
    capabilities: ['web_search', 'database_read', 'email_send'],
    provider: 'ollama',
    model: 'llama3',
    maxSteps: 8,
    allowWeb: true,
    allowFs: false,
    allowExec: false,
  },
  'Data Analysis Agent': {
    name: 'Data Analysis Agent',
    description: 'Reads internal datasets, produces reports and insights.',
    capabilities: ['database_read', 'file_read', 'chart_generate'],
    provider: 'ollama',
    model: 'mistral',
    maxSteps: 15,
    allowWeb: false,
    allowFs: true,
    allowExec: false,
  },
  'DevOps Automation Agent': {
    name: 'DevOps Automation Agent',
    description: 'Monitors CI/CD pipelines, auto-triages alerts, opens PRs.',
    capabilities: ['git_read', 'git_write', 'shell_exec', 'webhook_send'],
    provider: 'ollama',
    model: 'codellama',
    maxSteps: 20,
    allowWeb: true,
    allowFs: true,
    allowExec: true,
  },
  'Research Assistant': {
    name: 'Research Assistant',
    description: 'Searches the web, summarises papers, drafts reports.',
    capabilities: ['web_search', 'file_write', 'pdf_read'],
    provider: 'ollama',
    model: 'llama3',
    maxSteps: 12,
    allowWeb: true,
    allowFs: true,
    allowExec: false,
  },
}

export const INITIAL_AGENTS: AgentConfig[] = [
  {
    agentId: 'agt-7f3a9b',
    name: 'CodeReviewer-Alpha',
    description: 'Automated code review agent',
    capabilities: ['file_read', 'git_read'],
    provider: 'ollama',
    model: 'codellama',
    maxSteps: 10,
    allowWeb: false,
    allowFs: true,
    allowExec: false,
    trustScore: 94,
    status: 'active',
    registeredAt: '2026-06-20',
    owner: 'DevOps Team',
  },
  {
    agentId: 'agt-2e8c1d',
    name: 'DataAnalyst-Beta',
    description: 'Data analysis and reporting',
    capabilities: ['database_read', 'chart_generate'],
    provider: 'ollama',
    model: 'mistral',
    maxSteps: 15,
    allowWeb: false,
    allowFs: true,
    allowExec: false,
    trustScore: 87,
    status: 'active',
    registeredAt: '2026-06-21',
    owner: 'Data Science',
  },
  {
    agentId: 'agt-5b1f4e',
    name: 'SupportBot-Gamma',
    description: 'Customer support automation',
    capabilities: ['web_search', 'email_send'],
    provider: 'ollama',
    model: 'llama3',
    maxSteps: 8,
    allowWeb: true,
    allowFs: false,
    allowExec: false,
    trustScore: 45,
    status: 'suspended',
    registeredAt: '2026-06-22',
    owner: 'Support Team',
  },
]
