"""sandbox/pipeline.py — end-to-end pipeline orchestration tab."""
from __future__ import annotations

import time
import gradio as gr
from sandbox.state import SandboxState, AgentConfig, OperatorSession, TrustCert, AgentSession
from sandbox.agent_builder import PRESETS
from sandbox.clearframe_live import STEP_TEMPLATES


def _run_pipeline(state: SandboxState) -> tuple[str, str]:
    state.pipeline_log.clear()
    logs: list[str] = []

    def step(name: str, detail: str = "") -> None:
        state.log_pipeline(name, detail)
        logs.append(state.pipeline_log[-1])

    # 1. Agent Builder
    if not state.agent.agent_id:
        preset = PRESETS["Customer Support Bot"]
        state.agent = AgentConfig(
            agent_id=state.new_agent_id(),
            name="Customer Support Bot",
            description=preset["description"],
            capabilities=preset["capabilities"],
            provider="ollama",
            model=preset["model"],
            max_steps=preset["max_steps"],
            allow_web=preset["allow_web"],
            allow_fs=preset["allow_fs"],
            allow_exec=preset["allow_exec"],
        )
    step("Agent Builder", f"{state.agent.name} ({state.agent.agent_id})")

    # 2. SafePulse
    if not state.operator.verified:
        state.operator = OperatorSession(
            operator_id=state.new_agent_id().replace("agent", "op"),
            name="Pipeline Operator",
            verified=True,
            trust_score=0.95,
            auth_method="Pipeline Auto-Auth",
            timestamp=time.time(),
        )
    step("SafePulse", f"operator={state.operator.operator_id} score={state.operator.trust_score:.2f}")

    # 3. TrustRegistry
    if not state.cert or state.cert.revoked:
        issued_at = time.time()
        state.cert = TrustCert(
            cert_id=state.new_cert_id(),
            agent_id=state.agent.agent_id,
            trust_level="STANDARD",
            capabilities=state.agent.capabilities,
            issued_at=issued_at,
            expires_at=issued_at + 86400,
            revoked=False,
            signature=f"ed25519:pipeline-{int(issued_at)}",
        )
    step("TrustRegistry", f"cert={state.cert.cert_id}")

    # 4. ClearFrame
    session_id = state.new_session_id()
    state.session = AgentSession(
        session_id=session_id,
        agent_id=state.agent.agent_id,
        status="running",
        started_at=time.time(),
    )
    for i, (kind, source, msg, level) in enumerate(STEP_TEMPLATES, 1):
        ts = time.strftime("%H:%M:%S")
        state.session.steps.append({
            "step": i, "kind": kind, "source": source,
            "message": msg, "level": level, "timestamp": ts,
        })
        if level == "warn":
            alert = {"step": i, "severity": "MEDIUM", "message": msg, "source": source, "ts": ts}
            state.session.alerts.append(alert)
            state.sonar_events.append({"type": "drift", **alert})
    state.aegis_queue.append({
        "session_id": session_id,
        "agent_id": state.agent.agent_id,
        "agent_name": state.agent.name,
        "trust_level": state.cert.trust_level,
        "status": "pending",
        "registered_at": time.strftime("%H:%M:%S"),
    })
    step("ClearFrame", f"session={session_id} steps={len(STEP_TEMPLATES)}")

    # 5. Aegis + Sonar
    step("Aegis", "session queued for HITL review")
    step("Sonar", f"{len(state.sonar_events)} threat events recorded")

    summary = f"""
## ✅ Full Pipeline Complete

| Step | Status |
|---|---|
| Agent Builder | ✅ {state.agent.name} |
| SafePulse | ✅ Operator verified |
| TrustRegistry | ✅ {state.cert.cert_id} |
| ClearFrame | ✅ Session running |
| Aegis | ⏳ Pending HITL review |
| Sonar | ✅ Monitoring active |

Go to **Aegis HITL** to approve session `{session_id}`.
"""
    return summary, "\n".join(logs)


def build_pipeline_tab(state: SandboxState) -> None:
    gr.Markdown("""
## Full Pipeline — End-to-End Walkthrough

Runs every layer of the Erasys stack in sequence:
Agent Builder → SafePulse → TrustRegistry → ClearFrame → Sonar → Aegis
""")

    run_btn = gr.Button("▶️ Run Full Pipeline", variant="primary")
    summary_out = gr.Markdown()
    log_out = gr.Textbox(label="Pipeline log", lines=12, interactive=False)

    run_btn.click(
        fn=lambda: _run_pipeline(state),
        outputs=[summary_out, log_out],
    )
