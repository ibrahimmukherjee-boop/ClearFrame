"""Erasys Sandbox — Interactive PoC for AI Governance and Safety.

Tabs:
  1. Overview          — stack explainer + live architecture diagram
  2. Agent Builder     — build & configure ClearFrame agents
  3. SafePulse         — simulate biometric operator authentication
  4. TrustRegistry     — issue, verify, revoke agent trust certificates
  5. ClearFrame Live   — run an agent session with real-time monitoring
  6. Sonar SOC         — LLM threat detection & alert console
  7. Aegis HITL        — human-in-the-loop approval / deny / terminate
  8. Full Pipeline     — end-to-end walkthrough (all steps in one flow)
  9. ROI Dashboard     — client-facing ROI & business case calculator
"""

from __future__ import annotations

import gradio as gr

from sandbox.overview import build_overview_tab
from sandbox.agent_builder import build_agent_builder_tab
from sandbox.safepulse import build_safepulse_tab
from sandbox.trust_registry import build_trust_registry_tab
from sandbox.clearframe_live import build_clearframe_tab
from sandbox.sonar import build_sonar_tab
from sandbox.aegis import build_aegis_tab
from sandbox.pipeline import build_pipeline_tab
from sandbox.roi import build_roi_tab
from sandbox.state import SandboxState

CSS = """
.erasys-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
    border-radius: 12px;
    padding: 24px 32px;
    margin-bottom: 16px;
    border: 1px solid #334155;
}
.erasys-header h1 { color: #f8fafc; font-size: 2rem; font-weight: 700; margin: 0; }
.erasys-header p  { color: #94a3b8; font-size: 1rem; margin: 6px 0 0; }
.stack-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin: 2px;
}
.badge-green  { background: #166534; color: #bbf7d0; }
.badge-blue   { background: #1e3a8a; color: #bfdbfe; }
.badge-purple { background: #4c1d95; color: #ede9fe; }
.badge-orange { background: #92400e; color: #fef3c7; }
.badge-red    { background: #7f1d1d; color: #fee2e2; }
.status-ok    { color: #22c55e; font-weight: 600; }
.status-warn  { color: #f59e0b; font-weight: 600; }
.status-fail  { color: #ef4444; font-weight: 600; }
.panel-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 16px;
}
"""

def build_app() -> gr.Blocks:
    state = SandboxState()

    with gr.Blocks(
        title="Erasys Sandbox — AI Governance and Safety PoC",
        css=CSS,
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.blue,
            secondary_hue=gr.themes.colors.slate,
            neutral_hue=gr.themes.colors.slate,
            font=gr.themes.GoogleFont("Inter"),
        ),
    ) as demo:
        gr.HTML("""
        <div class="erasys-header">
          <h1>&#x1F6E1;&#xFE0F; Erasys AI Governance and Safety &mdash; Sandbox&nbsp;PoC</h1>
          <p>Build agents, run them through the full trust pipeline, and explore every layer of the stack &mdash; live.</p>
          <div style="margin-top:12px">
            <span class="stack-badge badge-blue">SafePulse &mdash; WHO is the operator?</span>
            <span class="stack-badge badge-purple">TrustRegistry &mdash; IS the agent trusted?</span>
            <span class="stack-badge badge-green">ClearFrame &mdash; WHAT is the agent doing?</span>
            <span class="stack-badge badge-orange">Sonar &mdash; Real-time threat detection</span>
            <span class="stack-badge badge-red">Aegis &mdash; Human veto &amp; override</span>
          </div>
        </div>
        """)

        with gr.Tabs():
            with gr.Tab("Overview", id="tab_overview"):
                build_overview_tab(state)

            with gr.Tab("Agent Builder", id="tab_builder"):
                build_agent_builder_tab(state)

            with gr.Tab("SafePulse (sim)", id="tab_safepulse"):
                build_safepulse_tab(state)

            with gr.Tab("TrustRegistry", id="tab_trust"):
                build_trust_registry_tab(state)

            with gr.Tab("ClearFrame Live", id="tab_cf"):
                build_clearframe_tab(state)

            with gr.Tab("Sonar SOC", id="tab_sonar"):
                build_sonar_tab(state)

            with gr.Tab("Aegis HITL", id="tab_aegis"):
                build_aegis_tab(state)

            with gr.Tab("Full Pipeline", id="tab_pipeline"):
                build_pipeline_tab(state)

            with gr.Tab("ROI Dashboard", id="tab_roi"):
                build_roi_tab(state)

    return demo


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
