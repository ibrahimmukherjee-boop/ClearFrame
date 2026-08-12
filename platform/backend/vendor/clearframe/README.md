# NexusProtocol

> **Managed intelligence — the OS for AI agents.**

NexusProtocol is an open-source agent operating system: agents from **any
stack** (MCP · LangGraph · OpenAI Agents SDK · Microsoft Agent Framework ·
Google ADK · Amazon Bedrock · NVIDIA NIM · IBM watsonx) run inside a governed,
autonomous loop where every action is policy-checked, alignment-scored,
threat-scanned, and written to a tamper-evident audit chain — with humans in
command.

| Layer | Component | Role |
|-------|-----------|------|
| 01 Loop | **Autonomous loop** | plan→act→observe with what/why/how reasoning chunks |
| 02 Policy | **Policy Engine** | policy-as-code: EU AI Act, NIST AI RMF, OWASP LLM, ISO 42001 |
| 03 Isolation | **Reader/Actor** | untrusted content never reaches the executor |
| 04 Audit | **HMAC chain** | tamper-evident, verifiable via `clearframe audit-verify` |
| 05 Oversight | **Aegis HITL** | human approve/reject/terminate, fail-closed |
| 06 Trust | **TrustRegistry** | Ed25519 certificates, capability scopes, revocation |
| 07 Adapters | **Any stack in** | MCP · A2A · LangChain · OpenAI · Bedrock · REST |
| 08 Persistence | **Checkpoints** | crash-resumable sessions, replayable history |

ClearFrame is the open-source runtime core of NexusProtocol.

## Governance benchmark

```bash
clearframe bench
```

Eight adversarial + operational scenarios run through the real runtime
(deterministic planner, no model variance):

```
NexusProtocol          8/8   ← measured live
LangGraph 1.x          2/8   ← out-of-the-box (vendor docs, Aug 2026)
Bedrock AgentCore      2/8
MS Agent Framework     1/8
OpenAI Agents SDK      0/8
Claude Agent SDK       0/8
OpenClaw               0/8
```

Controls: destructive-tool denial · secret-exfiltration denial · human sign-off
for sensitive actions (fail-closed) · call budgets · undeclared-tool refusal ·
checkpoint/resume · tamper-evident audit · what/why/how reasoning record.

---

## Create an agent (any toolchain)

```bash
clearframe agent new my-agent          # scaffold my-agent.agent.yaml
clearframe agent validate my-agent.agent.yaml
clearframe agent packs                 # list policy packs
```

Agent specs are portable YAML — the same file runs via CLI, `POST /api/agents`,
or code. Tools can come from **any ecosystem**:

```python
from clearframe.adapters import MCPAdapter, LangChainAdapter, OpenAIToolsAdapter
from clearframe.policy import PolicyEngine
from clearframe import AgentSession, ClearFrameConfig

tools = MCPAdapter("https://your-mcp-server/mcp").as_tool_registry()   # MCP
# tools = LangChainAdapter([DuckDuckGoSearchRun()]).as_tool_registry() # LangChain/LangGraph
# tools = OpenAIToolsAdapter(defs, dispatcher).as_tool_registry()      # OpenAI/Microsoft
# tools = BedrockAdapter(agent_id="...").as_tool_registry()            # Amazon Bedrock
# tools = HTTPToolAdapter([...]).as_tool_registry()                    # NVIDIA NIM / IBM watsonx / REST

engine = PolicyEngine.with_packs("baseline", "eu-ai-act")
async with AgentSession(config, manifest, tool_registry=tools, policy_engine=engine) as s:
    await s.call_tool("web_search", query="...")
```

A2A: the gateway serves a spec-compliant AgentCard at
`/.well-known/agent-card.json` so external agents (Copilot Studio, Bedrock
AgentCore, Google ADK) can discover and delegate to ClearFrame.

## Policy-as-code

Shipped packs (`clearframe/policy/packs/`): `baseline`, `eu-ai-act`,
`nist-ai-rmf`, `owasp-llm`. Rules: tool allow/deny, domain scoping, data
guards (PII/secrets), HITL requirements, call budgets, trust-level gates.
Governance document: [docs/governance/AI-POLICY.md](docs/governance/AI-POLICY.md).

---

## Deploy on EC2 (one command)

```bash
git clone -b cursor/nexus-sandbox-demo-be86 https://github.com/ibrahimmukherjee-boop/ClearFrame.git
cd ClearFrame
bash clearframe/deploy/install-ec2.sh
```

Then open:

```
http://YOUR-EC2-PUBLIC-IP:8080/
```

**Login:** none (demo mode).  
**Security group:** allow inbound **TCP 8080**.

### Docker

```bash
docker compose up --build -d
# → http://YOUR-HOST:8080/
```

---

## Local run

```bash
# from repo root
pip install -e ./clearframe \
  -e ./nexus-sandbox/components/trust-registry \
  -e ./nexus-sandbox/components/aegis \
  -e ./nexus-sandbox/components/sonar

clearframe serve --host 0.0.0.0 --port 8080
```

Open **http://localhost:8080/** — branded control plane, no login.

---

## CLI

```
clearframe serve          # Full stack + UI (recommended)
clearframe start          # AgentOps API only (:7477)
clearframe ops-start      # Alias for start
clearframe audit-verify   # Verify audit HMAC chain
clearframe version
```

---

## Why ClearFrame?

| Problem with OpenClaw / MCP | ClearFrame |
|---|---|
| Prompt injection via mixed reader/actor | Reader/Actor isolation |
| Plaintext credentials | AES-256-GCM vault |
| No audit trail | HMAC-chained audit log |
| No declared goal | Goal Monitor + auto-pause |
| No operator control | Live control plane |

## License

Apache 2.0
