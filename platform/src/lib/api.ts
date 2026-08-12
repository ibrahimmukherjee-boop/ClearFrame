// Backend origin resolution (in priority order):
//   1. a runtime override the operator saved in the browser (Connect field),
//   2. the VITE_API_URL baked in at build time (e.g. GitHub Pages -> Render),
//   3. same-origin '/api' (single-container deploy).
const BACKEND_KEY = 'nexus_backend'

export function getBackend(): string {
  if (typeof localStorage !== 'undefined') return localStorage.getItem(BACKEND_KEY) || ''
  return ''
}

export function setBackend(url: string): void {
  if (typeof localStorage === 'undefined') return
  const clean = url.trim().replace(/\/+$/, '')
  if (clean) localStorage.setItem(BACKEND_KEY, clean)
  else localStorage.removeItem(BACKEND_KEY)
}

function apiBase(): string {
  const override = getBackend()
  if (override) return `${override}/api`
  return (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'
}

/** Absolute URL for an API path using the resolved backend. */
export function apiUrl(path: string): string {
  return `${apiBase()}${path}`
}

function authHeaders(): Record<string, string> {
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('erasys_access_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail || err.message || `API error ${res.status}`
    if (res.status === 401 && typeof localStorage !== 'undefined') {
      localStorage.removeItem('erasys_access_token')
      localStorage.removeItem('erasys_user')
      throw new Error('Session expired — please sign in again')
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const api = {
  getState: () => request<import('./sandbox-types').ApiState>('/state'),
  listAgents: () => request<import('./sandbox-types').AgentConfig[]>('/agents'),
  saveAgent: (body: Record<string, unknown>) => request<import('./sandbox-types').AgentConfig>('/agents', { method: 'POST', body: JSON.stringify(body) }),
  selectAgent: (agentId: string) => request<import('./sandbox-types').AgentConfig>(`/agents/${agentId}/select`, { method: 'POST' }),
  revokeAgent: (agentId: string) => request<{ status: string }>(`/agents/${agentId}`, { method: 'DELETE' }),
  getPresets: () => request<Record<string, unknown>>('/presets'),
  enrollSafepulse: (profile: number[]) => request<{ enrolled: boolean }>('/safepulse/enroll', { method: 'POST', body: JSON.stringify({ profile }) }),
  verifySafepulse: (profile: number[]) => request<{ success: boolean; score: number }>('/safepulse/verify', { method: 'POST', body: JSON.stringify({ profile }) }),
  resetSafepulse: () => request<{ status: string }>('/safepulse', { method: 'DELETE' }),
  issueCertificate: (trustLevel: string, ttlHours: number) =>
    request<{ ok: boolean; message: string; cert?: import('./sandbox-types').TrustCert }>('/trust/issue', {
      method: 'POST',
      body: JSON.stringify({ trustLevel, ttlHours }),
    }),
  verifyCertificate: () => request<{ ok: boolean; message: string }>('/trust/verify'),
  revokeCertificate: () => request<{ ok: boolean; message: string }>('/trust/revoke', { method: 'POST' }),
  startSession: () =>
    request<{ ok: boolean; message: string; session?: import('./sandbox-types').AgentSession; auditLog?: import('./sandbox-types').AuditEntry[] }>(
      '/sessions/start',
      { method: 'POST' },
    ),
  getAuditLog: () => request<import('./sandbox-types').AuditEntry[]>('/sessions/audit'),
  listToolCalls: () => request<import('./sandbox-types').ToolCall[]>('/aegis/calls'),
  approveToolCall: (id: string) => request<{ status: string }>(`/aegis/${id}/approve`, { method: 'POST' }),
  blockToolCall: (id: string) => request<{ status: string }>(`/aegis/${id}/block`, { method: 'POST' }),
  resetToolCalls: () => request<{ status: string }>('/aegis/reset', { method: 'POST' }),
  getThreats: () => request<{ events: import('./sandbox-types').ThreatEvent[]; score: number }>('/sonar/threats'),
  runPipeline: () => request<{ ok: boolean; message: string; pipelineLog?: string[] }>('/pipeline/run', { method: 'POST' }),
  resetSandbox: () => request<{ status: string }>('/pipeline/reset', { method: 'POST' }),
  verifyAudit: () => request<{ valid: boolean; count: number; message: string }>('/audit/verify'),
  calculateRoi: (agents: number, operators: number, reductionPct: number) =>
    request<import('./sandbox-types').RoiResult>('/roi/calculate', {
      method: 'POST',
      body: JSON.stringify({ agents, operators, reductionPct }),
    }),
  suspendAgent: (agentId: string) => request<import('./sandbox-types').AgentConfig>(`/agents/${agentId}/suspend`, { method: 'POST' }),
  activateAgent: (agentId: string) => request<import('./sandbox-types').AgentConfig>(`/agents/${agentId}/activate`, { method: 'POST' }),
  getToolCatalog: () => request<import('./sandbox-types').ToolCatalogEntry[]>('/tools/catalog'),
  getToolConnections: () => request<import('./sandbox-types').ToolConnection[]>('/tools/connections'),
  createConnection: (toolId: string, name: string, config?: Record<string, unknown>) =>
    request<import('./sandbox-types').ToolConnection>('/tools/connections', {
      method: 'POST',
      body: JSON.stringify({ toolId, name, config }),
    }),
  executeTool: (tool: string, args: Record<string, unknown>) =>
    request<Record<string, unknown>>('/tools/execute', { method: 'POST', body: JSON.stringify({ tool, args }) }),
  getGovernance: () => request<import('./sandbox-types').GovernanceDashboard>('/governance/dashboard'),
  collectEvidence: () => request<{ collected: number }>('/governance/evidence', { method: 'POST' }),
  exportEvidence: () => request<Record<string, unknown>>('/governance/export'),
  getEuAiAct: () => request<Record<string, unknown>>('/eu-ai-act'),
  getRtlTrace: () => request<Array<{ step: number; tool: string; action: string; status: string; alignment: number }>>('/sessions/rtl'),
  listWorkflows: () => request<Array<Record<string, unknown>>>('/workflows'),
  createWorkflow: (body: Record<string, unknown>) => request<Record<string, unknown>>('/workflows', { method: 'POST', body: JSON.stringify(body) }),
  runWorkflow: (id: string) => request<Record<string, unknown>>(`/workflows/${id}/run`, { method: 'POST' }),
  listRuntimePolicies: () => request<Array<Record<string, unknown>>>('/policies'),
  setVaultSecret: (key: string, value: string) => request<{ status: string }>('/vault', { method: 'POST', body: JSON.stringify({ key, value }) }),
  getGovernanceHub: () => request<Record<string, unknown>>('/governance/hub'),
  attestFramework: (id: string, attested: boolean, notes?: string) =>
    request<Record<string, unknown>>(`/governance/frameworks/${id}/attest`, { method: 'POST', body: JSON.stringify({ attested, notes: notes || '' }) }),
  uploadPolicy: (body: Record<string, unknown>) => request<Record<string, unknown>>('/governance/documents', { method: 'POST', body: JSON.stringify(body) }),
  createPolicyCard: (body: Record<string, unknown>) => request<Record<string, unknown>>('/governance/cards', { method: 'POST', body: JSON.stringify(body) }),
  updateCardHierarchy: (cardId: string, parentCardId: string | null, hierarchyOrder: number, enforce?: boolean) =>
    request<Record<string, unknown>>(`/governance/cards/${cardId}/hierarchy?parentCardId=${parentCardId || ''}&hierarchyOrder=${hierarchyOrder}${enforce !== undefined ? `&enforce=${enforce}` : ''}`, { method: 'PATCH' }),
  getAgentActions: (sessionId?: string) => request<Array<Record<string, unknown>>>(`/governance/actions${sessionId ? `?sessionId=${sessionId}` : ''}`),
  getReasoningChain: (sessionId?: string) => request<Array<Record<string, unknown>>>(`/governance/reasoning${sessionId ? `?sessionId=${sessionId}` : ''}`),
  overrideToolCall: (id: string, note: string) => request<{ status: string }>(`/aegis/${id}/override`, { method: 'POST', body: JSON.stringify({ note, operatorId: 'operator' }) }),
}
