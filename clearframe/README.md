# ClearFrame

> The open-source AI agent protocol built for auditability, safety, and control.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

ClearFrame is a drop-in alternative to OpenClaw and MCP that puts **you** in control of your AI agents. Every tool call is scored for alignment, every reasoning step is captured, every credential is encrypted, and every action is logged to a tamper-evident audit trail.

---

## Why ClearFrame?

| Problem with OpenClaw / MCP | ClearFrame's answer |
|---|---|
| Single process reads untrusted content AND executes tools → prompt injection | **Reader/Actor isolation** — two sandboxed processes, typed pipe between them |
| Credentials stored in plaintext `~/.env` | **Encrypted Vault** — AES-256-GCM, memory-locked, auto-locks on session end |
| No audit trail — forensics impossible | **HMAC-chained Audit Log** — tamper-evident, cryptographically verifiable |
| No concept of what the agent is *supposed* to do | **Goal Monitor** — every tool call scored for alignment; drift triggers auto-pause |
| Chain-of-thought never captured | **Reasoning Transparency Layer (RTL)** — full trace as queryable JSON |
| No visibility into what context the model received | **Context Feed Auditor** — every token source-tagged and hashed |
| No operator control plane | **AgentOps** — live REST + WebSocket dashboard to approve, block, or tweak |
| Plugin ecosystem with no signing or review | **Signed Plugin Registry** — Ed25519 signatures, hash pinning, sandboxed execution |

---

## Quick Start

```bash
pip install clearframe

# Initialise a new agent project
clearframe init my-agent
cd my-agent

# Edit agent.py, then run
python agent.py
```

### Minimal example

```python
import asyncio
from clearframe import AgentSession, ClearFrameConfig
from clearframe.core.manifest import GoalManifest, ToolPermission

async def main():
    config = ClearFrameConfig()
    manifest = GoalManifest(
        goal="Search for the latest AI safety papers and summarise them",
        permitted_tools=[
            ToolPermission(tool_name="web_search", max_calls_per_session=5),
        ],
    )
    async with AgentSession(config, manifest) as session:
        result = await session.call_tool("web_search", query="AI safety 2026")
        print(result)

asyncio.run(main())
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AgentSession                           │
│                                                             │
│  ┌──────────────┐   typed pipe   ┌──────────────────────┐  │
│  │ ReaderSandbox│ ─────────────► │    ActorSandbox       │  │
│  │ (untrusted   │                │ (tool execution only) │  │
│  │  content)    │                │ never reads raw input │  │
│  └──────────────┘                └──────────────────────┘  │
│         │                                  │                │
│         ▼                                  ▼                │
│  ┌──────────────┐              ┌───────────────────────┐   │
│  │Context Feed  │              │     Goal Monitor       │   │
│  │Auditor       │              │  alignment scoring     │   │
│  │source-tags + │              │  auto-pause on drift   │   │
│  │hashes every  │              │  operator queue        │   │
│  │token         │              └───────────────────────┘   │
│  └──────────────┘                          │                │
│                                            ▼                │
│                              ┌───────────────────────┐     │
│                              │  RTL (Reasoning        │     │
│                              │  Transparency Layer)   │     │
│                              │  hash-verified traces  │     │
│                              └───────────────────────┘     │
│                                            │                │
│                                            ▼                │
│                              ┌───────────────────────┐     │
│                              │  HMAC-Chained Audit   │     │
│                              │  Log (tamper-evident) │     │
│                              └───────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                              ┌───────────────────────┐
                              │    AgentOps Server     │
                              │  REST + WebSocket      │
                              │  localhost:7477        │
                              └───────────────────────┘
```

---

## Core Concepts

### GoalManifest
Declare **what the agent is allowed to do** before it starts. The runtime enforces it.

```python
from clearframe.core.manifest import GoalManifest, ToolPermission, ResourceScope

manifest = GoalManifest(
    goal="Book a flight to London for next Friday",
    permitted_tools=[
        ToolPermission(tool_name="web_search", max_calls_per_session=10),
        ToolPermission(tool_name="web_fetch", max_calls_per_session=5),
        ToolPermission(tool_name="send_email", max_calls_per_session=1, require_approval=True),
    ],
    allow_file_write=False,
    allow_code_execution=False,
    max_steps=30,
    resource_scope=ResourceScope(
        allowed_domains=["flights.example.com", "*.airline.com"],
    ),
)
```

### Vault
Never store credentials in plaintext again.

```python
from clearframe.core.vault import Vault
from clearframe.core.config import VaultConfig

vault = Vault(VaultConfig())
vault.unlock("your-master-password")
vault.set("openai_api_key", "sk-...")
key = vault.get("openai_api_key")
vault.lock()  # auto-zeroises memory
```

### Audit Log
Cryptographically verify nothing was tampered with.

```bash
clearframe audit-verify
# ✓ Audit log integrity verified — no tampering detected.

clearframe audit-tail --lines 50
```

### AgentOps Server
Start the live control plane:

```bash
clearframe ops-start
# AgentOps running at http://localhost:7477
# Auth token: <printed once to console>
```

---

## CLI Reference

```
clearframe init <name>          Create a new agent project
clearframe audit-verify         Verify audit log HMAC chain integrity
clearframe audit-tail           Show recent audit entries
clearframe ops-start            Start AgentOps control plane
clearframe version              Show version
```

---

## Comparison vs OpenClaw / MCP

| Feature | OpenClaw | MCP | **ClearFrame** |
|---|---|---|---|
| Reader/Actor isolation | ✗ | ✗ | ✅ |
| Goal alignment scoring | ✗ | ✗ | ✅ |
| Reasoning trace capture | ✗ | Partial | ✅ Full JSON |
| Tamper-evident audit log | ✗ | ✗ | ✅ HMAC chain |
| Encrypted credential vault | ✗ | ✗ | ✅ AES-256-GCM |
| Context feed hashing | ✗ | ✗ | ✅ |
| Live operator control plane | ✗ | ✗ | ✅ |
| Signed plugin registry | ✗ | ✗ | ✅ Ed25519 |
| Auto-pause on drift | ✗ | ✗ | ✅ |
| Open source | ✅ | ✅ | ✅ Apache 2.0 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome — open an issue first for large changes.

## License

Apache 2.0 — see [LICENSE](LICENSE).
