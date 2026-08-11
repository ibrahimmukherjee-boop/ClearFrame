# ClearFrame AI Governance Policy

**Version 1.0 · Nexus Protocol · Applies to every agent executed by the ClearFrame runtime**

This document is the operator-facing AI policy for ClearFrame deployments. It is
enforced in code by the ClearFrame Policy Engine (`clearframe.policy`), the Goal
Monitor, Sonar threat detection, Aegis human oversight, and the TrustRegistry.
Each control below names the mechanism that enforces it.

---

## 1. Purpose and scope

ClearFrame is an agent operating system: it executes AI agents that call tools.
This policy defines the rules every agent must satisfy before, during, and
after execution. It applies to agents built natively and to agents imported
from external ecosystems (MCP, LangChain/LangGraph, OpenAI Agents SDK,
Microsoft Agent Framework, Amazon Bedrock, Google ADK, NVIDIA NIM, IBM
watsonx) via ClearFrame adapters.

## 2. Principles

1. **Declared intent** — no agent runs without a signed GoalManifest stating
   its goal, permitted tools, and resource scope. *(Enforced: manifest lock)*
2. **Least agency** — agents get the minimum tool surface required. Deny-by-
   default for destructive operations. *(Enforced: policy packs `tools.deny`)*
3. **Human primacy** — irreversible, financial, or legally significant actions
   require human approval before execution. *(Enforced: `actions.require_approval`
   → Aegis HITL queue)*
4. **Total auditability** — every tool call, decision, and context chunk is
   recorded in a tamper-evident HMAC-chained audit log. *(Enforced: AuditLog)*
5. **Verified identity** — agents carry Ed25519 trust certificates with
   capability scopes and revocation. *(Enforced: TrustRegistry)*
6. **Continuous threat monitoring** — inputs and outputs are scanned for
   prompt injection, data exfiltration, and policy drift. *(Enforced: Sonar)*

## 3. Policy packs

Policy is code. Packs ship in `clearframe/policy/packs/` and can be combined:

| Pack | Regime | What it enforces |
|------|--------|------------------|
| `baseline` | ClearFrame defaults | destructive-tool deny list, secret/PII guards, HITL for irreversible actions, per-tool budgets |
| `eu-ai-act` | EU AI Act (Reg. 2024/1689) | Art. 5 prohibited practices blocked at tool level; Art. 14 human oversight; Art. 12 logging; special-category data guards |
| `nist-ai-rmf` | NIST AI RMF 1.0 + GenAI Profile | MANAGE 2.4 deactivation, MEASURE 2.7 security controls, PII patterns |
| `owasp-llm` | OWASP LLM Top 10 (2025) | LLM02 disclosure guards, LLM06 excessive-agency limits, LLM10 consumption limits |

Custom packs: any YAML file with the same schema, loaded via
`PolicyEngine.with_packs(..., extra_paths=[...])`.

## 4. Regulatory mapping

### EU AI Act (Regulation (EU) 2024/1689)

| Obligation | Article | ClearFrame mechanism |
|------------|---------|----------------------|
| Risk management system | Art. 9 | Goal Monitor scoring + auto-pause; policy packs |
| Record-keeping | Art. 12 | HMAC-chained audit log; RTL reasoning traces |
| Transparency to deployers | Art. 13 | AgentSpec (portable YAML), audit-verify CLI |
| Human oversight | Art. 14 | Aegis HITL approve/reject/terminate with timeouts |
| Accuracy, robustness, cybersecurity | Art. 15 | Sonar scanning; Reader/Actor isolation; encrypted vault |
| Deployer duties (monitor + suspend) | Art. 26 | Goal Monitor drift detection; session suspension |
| Prohibited practices | Art. 5 | `eu-ai-act` pack tool deny list |

### NIST AI RMF 1.0

| Function | ClearFrame mechanism |
|----------|----------------------|
| GOVERN | This policy document; TrustRegistry certificate authority |
| MAP | AgentSpec declares context, goal, tools, and trust level |
| MEASURE | Goal alignment scores; Sonar threat events; audit metrics |
| MANAGE | Policy engine decisions; auto-pause; Aegis termination |

### OWASP LLM Top 10 (2025)

| Risk | ClearFrame mechanism |
|------|----------------------|
| LLM01 Prompt injection | Sonar injection patterns; Reader/Actor isolation |
| LLM02 Sensitive information disclosure | `data.deny_patterns` guards |
| LLM05 Improper output handling | Sonar output scans before delivery |
| LLM06 Excessive agency | Manifest tool permissions; `tools.allow` lists |
| LLM08 Vector/embedding weaknesses | Context Feed Auditor source-tagging |
| LLM10 Unbounded consumption | `limits.max_calls_per_tool`; max_steps |

## 5. Lifecycle requirements

1. **Creation** — agents are created from an AgentSpec (YAML). The spec names
   its policy packs; specs without packs get `baseline` automatically.
2. **Registration** — production agents obtain a TrustRegistry certificate at
   or above the level their policy packs demand (`trust.min_level`).
3. **Execution** — every tool call passes: Policy Engine → Goal Monitor →
   (optional) Aegis HITL → Actor sandbox. Denials are audited.
4. **Monitoring** — Sonar scans context and outputs continuously; three
   consecutive low-alignment calls suspend the session.
5. **Retirement** — revoking the trust certificate immediately invalidates the
   agent; audit logs are retained per deployer retention policy.

## 6. Incident response

- Sonar `critical` events block the action and page the operator (control plane).
- Aegis timeout without human decision = automatic rejection (fail-closed).
- Audit chain verification failures are treated as security incidents.

## 7. Review

This policy and the shipped packs are reviewed quarterly against: EU AI Act
implementing acts, NIST AI RMF updates, OWASP LLM Top 10 revisions, and MCP /
A2A specification changes.
