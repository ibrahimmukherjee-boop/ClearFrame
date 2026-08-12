"""sandbox/aegis.py — Aegis human-in-the-loop oversight tab."""
from __future__ import annotations

import time
import gradio as gr
from sandbox.state import SandboxState


def _queue_status(state: SandboxState) -> str:
    if not state.aegis_queue:
        return "No sessions in the Aegis queue. Start a **ClearFrame Live** session first."
    lines = ["## Aegis HITL Queue\n"]
    for item in state.aegis_queue:
        lines.append(
            f"- `{item['session_id']}` — **{item['agent_name']}** "
            f"[{item['trust_level']}] — status: **{item['status']}** "
            f"(registered {item['registered_at']})"
        )
    return "\n".join(lines)


def _approve_session(state: SandboxState, session_id: str) -> str:
    item = next((q for q in state.aegis_queue if q["session_id"] == session_id), None)
    if not item:
        return f"❌ Session `{session_id}` not found in queue."
    item["status"] = "approved"
    if state.session and state.session.session_id == session_id:
        state.session.status = "approved"
    state.log_pipeline("Aegis: approved", session_id)
    return f"✅ Session `{session_id}` **approved**. Agent may continue execution."


def _deny_session(state: SandboxState, session_id: str) -> str:
    item = next((q for q in state.aegis_queue if q["session_id"] == session_id), None)
    if not item:
        return f"❌ Session `{session_id}` not found in queue."
    item["status"] = "denied"
    if state.session and state.session.session_id == session_id:
        state.session.status = "denied"
        state.session.ended_at = time.time()
    state.log_pipeline("Aegis: denied", session_id)
    return f"🚫 Session `{session_id}` **denied**. Agent execution terminated."


def _terminate_session(state: SandboxState, session_id: str) -> str:
    item = next((q for q in state.aegis_queue if q["session_id"] == session_id), None)
    if not item:
        return f"❌ Session `{session_id}` not found in queue."
    item["status"] = "terminated"
    if state.session and state.session.session_id == session_id:
        state.session.status = "terminated"
        state.session.ended_at = time.time()
    state.log_pipeline("Aegis: terminated", session_id)
    return f"⛔ Session `{session_id}` **terminated** by operator override."


def build_aegis_tab(state: SandboxState) -> None:
    gr.Markdown("""
## Aegis — Human-in-the-Loop Oversight

Aegis answers *SHOULD the agent do this?*  
Operators review, approve, deny, or terminate agent sessions in real time.
""")

    refresh_btn = gr.Button("🔄 Refresh Queue", variant="secondary")
    queue_out = gr.Markdown()

    with gr.Row():
        session_id = gr.Textbox(label="Session ID", placeholder="sess-xxxxxxxx")
    with gr.Row():
        approve_btn = gr.Button("✅ Approve", variant="primary")
        deny_btn = gr.Button("🚫 Deny", variant="stop")
        terminate_btn = gr.Button("⛔ Terminate", variant="stop")

    action_out = gr.Markdown()

    refresh_btn.click(fn=lambda: _queue_status(state), outputs=[queue_out])
    approve_btn.click(fn=lambda sid: _approve_session(state, sid), inputs=[session_id], outputs=[action_out])
    deny_btn.click(fn=lambda sid: _deny_session(state, sid), inputs=[session_id], outputs=[action_out])
    terminate_btn.click(fn=lambda sid: _terminate_session(state, sid), inputs=[session_id], outputs=[action_out])
