"""sandbox/clearframe_live.py — ClearFrame runtime monitoring tab."""
from __future__ import annotations
import random
import time
import gradio as gr
from sandbox.state import SandboxState, AgentSession

STEP_TEMPLATES = [
    ("tool_call",       "web_search",   "Searching for relevant information",     "normal"),
    ("tool_call",       "database_read","Querying customer records",               "normal"),
    ("llm_call",        "llm_reason",   "Reasoning about next action",             "normal"),
    ("tool_call",       "file_read",    "Reading internal config file",            "normal"),
    ("goal_check",      "goal_monitor", "GoalMonitor: task aligns with objective", "ok"),
    ("tool_call",       "email_send",   "Drafting email response to customer",     "normal"),
    ("drift_alert",     "clearframe",   "ClearFrame: mild behavioural drift detected","warn"),
    ("tool_call",       "web_search",   "Second search for verification",          "normal"),
    ("goal_check",      "goal_monitor", "GoalMonitor: sub-goal completed",         "ok"),
    ("rtl_check",       "rtl",          "RTL: agent within permitted action scope","ok"),
    ("llm_call",        "llm_reason",   "Composing final answer",                  "normal"),
    ("session_end",     "clearframe",   "Session completed successfully",           "ok"),
]


def _start_session(state: SandboxState) -> tuple[str, str]:
    if not state.agent.agent_id:
        return "❌ No agent defined.", ""
    if not state.operator.verified:
        return "❌ Operator not verified via SafePulse.", ""
    if not state.cert or state.cert.revoked:
        return "❌ No valid TrustRegistry certificate.", ""

    session_id = state.new_session_id()
    state.session = AgentSession(
        session_id=session_id,
        agent_id=state.agent.agent_id,
        status="running",
        started_at=time.time(),
    )
    # Add to Aegis queue for HITL approval
    state.aegis_queue.append({
        "session_id": session_id,
        "agent_id":   state.agent.agent_id,
        "agent_name": state.agent.name,
        "trust_level": state.cert.trust_level if state.cert else "UNKNOWN",
        "status":     "pending",
        "registered_at": time.strftime("%H:%M:%S"),
    })
    state.log_pipeline("ClearFrame: session started", session_id)

    # Simulate steps
    steps_md = []
    alert_count = 0
    for i, (kind, source, msg, level) in enumerate(STEP_TEMPLATES, 1):
        ts = time.strftime("%H:%M:%S")
        icon = {"normal": "🔵", "ok": "✅", "warn": "⚠️", "error": "❌"}.get(level, "🔵")
        step = {
            "step": i, "kind": kind, "source": source,
            "message": msg, "level": level, "timestamp": ts,
        }
        state.session.steps.append(step)

        if level == "warn":
            alert = {"step": i, "severity": "MEDIUM", "message": msg, "source": source, "ts": ts}
            state.session.alerts.append(alert)
            state.sonar_events.append({"type": "drift", **alert})
            alert_count += 1

        steps_md.append(f"{icon} **[{ts}]** `{source}` — {msg}")

    session_md = f"""
## ▶️ Session Running: `{session_id}`

| Field | Value |
|---|---|
| **Agent** | {state.agent.name} (`{state.agent.agent_id}`) |
| **Model** | {state.agent.model} |
| **Trust level** | {state.cert.trust_level} |
| **Steps** | {len(STEP_TEMPLATES)} |
| **Alerts** | {alert_count} |
| **Status** | running → awaiting Aegis approval |

### Step-by-step trace
"""
    session_md += "\n".join(steps_md)
    session_md += "\n\n> ⚠️ Session is in the **Aegis queue** — go to the **Aegis HITL** tab to approve or deny."

    return session_md, f"Session `{session_id}` registered with Aegis for HITL review."


def _get_session_status(state: SandboxState) -> str:
    if not state.session:
        return "No active session."
    s = state.session
    alerts = len(s.alerts)
    return f"""
| Field | Value |
|---|---|
| **Session ID** | `{s.session_id}` |
| **Status** | **{s.status}** |
| **Steps completed** | {len(s.steps)} |
| **Alerts** | {alerts} |
"""


def build_clearframe_tab(state: SandboxState) -> None:
    gr.Markdown("""
## ClearFrame — Runtime Agent Governance

ClearFrame answers *WHAT is the agent doing?*  
It records every tool call, LLM interaction, and behavioural feature in real time,
running GoalMonitor (goal alignment) and RTL (Return-to-Limits) checks continuously.
""")

    with gr.Row():
        start_btn  = gr.Button("▶️ Start Agent Session", variant="primary")
        status_btn = gr.Button("🔄 Refresh Status", variant="secondary")

    session_out = gr.Markdown()
    status_out  = gr.Markdown()

    start_btn.click(
        fn=lambda: _start_session(state),
        outputs=[session_out, status_out],
    )
    status_btn.click(
        fn=lambda: _get_session_status(state),
        outputs=[status_out],
    )
