# Erasys ClearFrame — Enterprise Platform Briefing

**Document purpose:** Pre-meeting summary for stakeholders reviewing the ClearFrame AI Governance and Safety pilot environment.

**Companion strategy PDF:** `Erasys-Governance-as-Code-Enterprise-Briefing.pdf`

---

## Access

| Item | Value |
|------|-------|
| **URL** | http://52.91.66.29 |
| **DNS** | http://ec2-52-91-66-29.compute-1.amazonaws.com |
| **Email** | admin@erasys.local |
| **Password** | See `~/Desktop/ClearFrame-Demo-Access.txt` |
| **Note** | Use **HTTP** (not HTTPS) on this demo host to avoid browser certificate warnings |
| **Uptime** | Instance `i-08d17d775371f32f1` — Docker `restart: unless-stopped` + systemd watchdog |

---

## What ClearFrame Is

ClearFrame is a **governed AI control plane** (Governance Overlay / Governance-as-Code) designed to demonstrate how an enterprise can:

- Register and configure AI agents with scoped capabilities
- Upload internal and supplier policies; parse them into enforceable rules (GoverUp)
- Enforce policy before tool execution (deny, require human approval, or allow)
- Maintain a tamper-evident audit trail and governance evidence for ISO 42001, EU AI Act, and GDPR

This deployment is a **pilot demonstration environment**, not production estate-wide rollout.

---

## What Works in This Demo

- Sign-in and role-based access
- Agent Builder — create and save agents
- Governance Hub — upload policies, auto-parse into policy cards, attest frameworks
- Human-in-the-loop — approve, block, or override agent actions
- Audit log and reasoning chain from pipeline/agent sessions
- Vault, workflows, and platform metrics from live database state

---

## Honest Scope Limits

| Limitation | Detail |
|------------|--------|
| **Single-server pilot** | Agents run on one demo server; not deployed across the organisation |
| **Demo LLM backend** | Uses configured provider; not connected to enterprise model gateways by default |
| **No enterprise IdP** | SSO/OIDC hooks exist but are not connected in this pilot |
| **Not ISO certified** | Platform collects technical evidence; certification requires external audit |
| **HTTP demo host** | Trusted HTTPS requires a domain and CA-issued certificate |

---

## Recommended Talking Point

> *Erasys is the Governance-as-Code overlay for agentic AI — border control for who builds, who operates, what agents are trusted to do, and how every high-risk action is approved and audited. We do not replace your cloud AI platform or ERP. We make it safe to scale agents on top of them.*
