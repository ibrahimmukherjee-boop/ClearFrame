"""sandbox/trust_registry.py — TrustRegistry simulator tab.

In production, TrustRegistry issues Ed25519-signed trust certificates
to AI agents, enforces capability scopes, and provides a CRL.
This module replicates the full API flow using in-memory simulation.
"""
from __future__ import annotations
import hashlib
import time
import gradio as gr
from sandbox.state import SandboxState, TrustCert

TRUST_LEVELS = {
    "SANDBOX":    "Development only. No production access.",
    "RESTRICTED": "Limited prod access. Requires human approval per session.",
    "STANDARD":   "Normal production agent. Automated monitoring active.",
    "ELEVATED":   "High-privilege agent. Enhanced monitoring + HITL approval required.",
    "CRITICAL":   "Maximum privilege. Dual-operator sign-off required.",
}


def _issue_cert(state: SandboxState, trust_level: str, ttl_hours: int) -> tuple[str, str]:
    if not state.agent.agent_id:
        return "❌ No agent defined. Go to **Agent Builder** first.", ""
    if not state.operator.verified:
        return "❌ Operator not verified. Complete **SafePulse** authentication first.", ""

    cert_id = state.new_cert_id()
    issued_at = time.time()
    expires_at = issued_at + (ttl_hours * 3600)

    # Simulated Ed25519 signature (SHA-256 of key fields)
    sig_input = f"{cert_id}:{state.agent.agent_id}:{trust_level}:{issued_at}"
    signature = "ed25519:" + hashlib.sha256(sig_input.encode()).hexdigest()[:32]

    state.cert = TrustCert(
        cert_id=cert_id,
        agent_id=state.agent.agent_id,
        trust_level=trust_level,
        capabilities=state.agent.capabilities,
        issued_at=issued_at,
        expires_at=expires_at,
        revoked=False,
        signature=signature,
    )
    state.log_pipeline("TrustRegistry: cert issued", f"{cert_id} level={trust_level}")

    caps = ", ".join(state.agent.capabilities) or "(none)"
    issued_str  = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(issued_at))
    expires_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(expires_at))

    cert_md = f"""
## ✅ Trust Certificate Issued

```
CERTIFICATE
  ID:          {cert_id}
  Agent:       {state.agent.name} ({state.agent.agent_id})
  Operator:    {state.operator.name} ({state.operator.operator_id})
  Trust level: {trust_level}
  Capabilities:{caps}
  Issued:      {issued_str}
  Expires:     {expires_str}
  Signature:   {signature}
  Revoked:     false
```

**Trust level**: {trust_level} — {TRUST_LEVELS[trust_level]}
"""
    return cert_md, "Proceed to **ClearFrame Live** to start the agent session."


def _verify_cert(state: SandboxState) -> str:
    c = state.cert
    if not c:
        return "❌ No certificate in state. Issue one first."
    if c.revoked:
        return f"❌ Certificate `{c.cert_id}` is REVOKED."
    if time.time() > c.expires_at:
        return f"❌ Certificate `{c.cert_id}` has EXPIRED."
    return f"✅ Certificate `{c.cert_id}` is VALID. Agent `{c.agent_id}` is authorised at trust level **{c.trust_level}**."


def _revoke_cert(state: SandboxState) -> str:
    if not state.cert:
        return "❌ No certificate to revoke."
    state.cert.revoked = True
    state.log_pipeline("TrustRegistry: cert revoked", state.cert.cert_id)
    return f"⚠️ Certificate `{state.cert.cert_id}` has been REVOKED and added to the CRL."


def build_trust_registry_tab(state: SandboxState) -> None:
    gr.Markdown("""
## TrustRegistry — AI Agent PKI Certificate Authority

TrustRegistry answers *IS this agent trusted?*  
It issues Ed25519-signed certificates that scope exactly what an agent is allowed to do.
""")

    with gr.Tabs():
        with gr.Tab("Issue Certificate"):
            with gr.Row():
                trust_level = gr.Dropdown(
                    label="Trust level",
                    choices=list(TRUST_LEVELS.keys()),
                    value="STANDARD",
                )
                ttl = gr.Slider(label="TTL (hours)", minimum=1, maximum=168, step=1, value=24)
            issue_btn = gr.Button("🏷️ Issue Certificate", variant="primary")
            cert_out  = gr.Markdown()
            next_md   = gr.Markdown()

            issue_btn.click(
                fn=lambda tl, ttl: _issue_cert(state, tl, ttl),
                inputs=[trust_level, ttl],
                outputs=[cert_out, next_md],
            )

        with gr.Tab("Verify Certificate"):
            verify_btn = gr.Button("🔍 Verify Current Certificate", variant="secondary")
            verify_out = gr.Markdown()
            verify_btn.click(
                fn=lambda: _verify_cert(state),
                outputs=[verify_out],
            )

        with gr.Tab("Revoke Certificate"):
            gr.Markdown("⚠️ Revoking a certificate immediately invalidates the agent session.")
            revoke_btn = gr.Button("🚫 Revoke Certificate", variant="stop")
            revoke_out = gr.Markdown()
            revoke_btn.click(
                fn=lambda: _revoke_cert(state),
                outputs=[revoke_out],
            )
