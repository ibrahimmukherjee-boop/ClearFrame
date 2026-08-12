"""sandbox/sonar.py — Sonar SOC threat detection tab."""
from __future__ import annotations

import random
import time
import gradio as gr
from sandbox.state import SandboxState

THREAT_TEMPLATES = [
    ("policy_violation", "HIGH", "Attempted file access outside allowed scope"),
    ("anomaly", "MEDIUM", "Unusual query pattern detected"),
    ("credential_abuse", "CRITICAL", "API key used from unknown IP range"),
    ("insider_threat", "LOW", "Off-hours activity pattern"),
    ("drift", "MEDIUM", "ClearFrame: mild behavioural drift detected"),
]


def _inject_threat(state: SandboxState, threat_type: str, severity: str, message: str) -> str:
    event = {
        "id": f"evt-{len(state.sonar_events) + 1}",
        "timestamp": time.strftime("%H:%M:%S"),
        "agent": state.agent.name or "unknown-agent",
        "type": threat_type,
        "severity": severity,
        "message": message,
    }
    state.sonar_events.insert(0, event)
    state.log_pipeline("Sonar: threat detected", f"{threat_type} ({severity})")
    return f"🚨 Alert injected: **{threat_type}** [{severity}] — {message}"


def _scan_session(state: SandboxState) -> str:
    if not state.session:
        return "❌ No active session to scan."

    alerts = state.session.alerts
    if not alerts:
        return f"✅ Session `{state.session.session_id}` clean — no threats detected."

    lines = [f"## Sonar Scan — {len(alerts)} alert(s)\n"]
    for a in alerts:
        lines.append(f"- **[{a['severity']}]** {a['message']} (step {a['step']})")
    state.log_pipeline("Sonar: session scan", f"{len(alerts)} alerts")
    return "\n".join(lines)


def _threat_feed(state: SandboxState) -> str:
    if not state.sonar_events:
        return "No threat events yet. Start a ClearFrame session or inject a test alert."
    lines = ["## Live Threat Feed\n"]
    for e in state.sonar_events[:10]:
        lines.append(
            f"- `{e['timestamp']}` **[{e['severity']}]** {e['type']} — {e['message']} "
            f"(agent: {e.get('agent', 'unknown')})"
        )
    threat_score = min(95, 30 + len(state.sonar_events) * 8 + random.randint(0, 10))
    lines.append(f"\n**Threat level**: {threat_score}%")
    return "\n".join(lines)


def build_sonar_tab(state: SandboxState) -> None:
    gr.Markdown("""
## Sonar — AI-Powered SOC

Sonar provides real-time threat detection across the agent ecosystem.
It ingests ClearFrame audit events and behavioural signals to surface anomalies.
""")

    with gr.Row():
        scan_btn = gr.Button("🔍 Scan Active Session", variant="primary")
        inject_btn = gr.Button("⚡ Inject Test Alert", variant="secondary")

    feed_btn = gr.Button("🔄 Refresh Threat Feed")
    output = gr.Markdown()

    scan_btn.click(fn=lambda: _scan_session(state), outputs=[output])
    inject_btn.click(
        fn=lambda: _inject_threat(state, *random.choice(THREAT_TEMPLATES)),
        outputs=[output],
    )
    feed_btn.click(fn=lambda: _threat_feed(state), outputs=[output])
