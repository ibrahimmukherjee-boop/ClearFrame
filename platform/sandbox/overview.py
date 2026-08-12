"""sandbox/overview.py — Overview tab: architecture diagram and stack explainer."""
from __future__ import annotations
import gradio as gr
from sandbox.state import SandboxState


ARCH_HTML = """
<div style="font-family:monospace; background:#0f172a; color:#e2e8f0; padding:24px; border-radius:10px; line-height:1.8; font-size:0.9rem;">
<pre style="margin:0; color:#e2e8f0;">
  OPERATOR (human)
       |
       v
  [1] SafePulse — biometric identity verification
       |  WHO is the operator? (typing cadence, mouse dynamics)
       |  ✔ Verified operator identity before anything runs
       v
  [2] TrustRegistry — AI Agent PKI / Certificate Authority
       |  IS this agent authorised? (Ed25519 trust cert)
       |  ✔ Capability scopes, expiry, revocation list (CRL)
       v
  [3] ClearFrame — open-source agentic runtime governance
       |  WHAT is the agent doing? (GoalMonitor, RTL, drift)
       |  ✔ Behavioural biometrics, session recording, audit
       v
  [4] Sonar — AI Security Operations Centre
       |  Real-time threat detection on every LLM call
       |  ✔ Prompt injection, data exfil, policy violations
       v
  [5] Aegis — Human-in-the-Loop control plane
            Operator approves / denies / terminates sessions
            ✔ Full audit trail, SafePulse-verified approvals
</pre>
</div>
"""

STACK_TABLE = """
| Product | Question answered | Key capability |
|---|---|---|
| **SafePulse** (simulated) | *WHO* is the operator? | Behavioural biometrics — typing & mouse patterns |
| **TrustRegistry** | *IS* the agent trusted? | Ed25519 PKI certs, CRL, capability scopes |
| **ClearFrame** (open-source) | *WHAT* is the agent doing? | Runtime governance, GoalMonitor, RTL, audit log |
| **Sonar** | *Is anything malicious happening?* | Prompt injection, data exfil, anomaly detection |
| **Aegis** | *Should this continue?* | Human override, approve / deny / terminate |
"""

WHY_HTML = """
<div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:8px;">
  <div style="background:#1e293b; border:1px solid #334155; border-radius:8px; padding:16px;">
    <h3 style="color:#38bdf8; margin:0 0 8px;">Without the stack</h3>
    <ul style="color:#cbd5e1; margin:0; padding-left:18px;">
      <li>No operator identity verification</li>
      <li>Agents can impersonate or be hijacked</li>
      <li>No capability scoping or revocation</li>
      <li>No real-time threat detection</li>
      <li>No human override or kill switch</li>
      <li>Zero auditability for compliance</li>
    </ul>
  </div>
  <div style="background:#1e293b; border:1px solid #334155; border-radius:8px; padding:16px;">
    <h3 style="color:#4ade80; margin:0 0 8px;">With the Erasys stack</h3>
    <ul style="color:#cbd5e1; margin:0; padding-left:18px;">
      <li>Cryptographic operator identity before any action</li>
      <li>Every agent carries a revocable trust certificate</li>
      <li>Scoped capabilities — principle of least privilege</li>
      <li>Real-time injection & exfil detection via Sonar</li>
      <li>Instant human veto at any point via Aegis</li>
      <li>Immutable audit log for SOC2/ISO27001/GDPR</li>
    </ul>
  </div>
</div>
"""


def build_overview_tab(state: SandboxState) -> None:
    gr.HTML(ARCH_HTML)
    gr.Markdown("## Erasys AI Governance and Safety")
    gr.Markdown(STACK_TABLE)
    gr.HTML(WHY_HTML)
    gr.Markdown("""
---
### How to use this sandbox
1. **Agent Builder** — define your agent (name, capabilities, model).
2. **SafePulse** — simulate operator biometric authentication.
3. **TrustRegistry** — issue a trust certificate for your agent.
4. **ClearFrame Live** — run the agent and watch runtime monitoring.
5. **Sonar SOC** — inject threats and see detection in real time.
6. **Aegis HITL** — approve, deny, or terminate the session.
7. **Full Pipeline** — run the entire flow end-to-end in one click.
8. **ROI Dashboard** — see the business case tailored to your organisation.
""")
