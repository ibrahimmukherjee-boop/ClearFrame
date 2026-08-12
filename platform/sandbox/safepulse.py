"""sandbox/safepulse.py — SafePulse biometric authentication simulator.

SafePulse is a proprietary Erasys product.  This module *simulates* it
so the sandbox can demonstrate the full pipeline without the real service.
In production, SafePulse verifies operator identity via:
  - Keystroke dynamics (dwell / flight times)
  - Mouse movement trajectories
  - Scroll behaviour patterns
  - Multi-factor fallback (TOTP / FIDO2)
"""
from __future__ import annotations
import random
import time
import uuid
import gradio as gr
from sandbox.state import SandboxState, OperatorSession


AUTH_METHODS = {
    "Keystroke Dynamics": "typing cadence & dwell/flight time analysis",
    "Mouse Dynamics":     "cursor velocity, trajectory smoothness & click patterns",
    "Scroll Behaviour":   "scroll speed variance & rhythm fingerprint",
    "Combined (all three)": "full behavioural biometric profile (highest confidence)",
}

SCENARIOS = {
    "Normal operator — all checks pass":            (True,  0.97),
    "Low-confidence typing pattern (borderline)":   (True,  0.72),
    "Unknown user — behavioural mismatch":          (False, 0.31),
    "Replay attack detected — static signature":   (False, 0.18),
    "Compromised session — anomalous mouse input":  (False, 0.22),
}


def _simulate_auth(
    state: SandboxState,
    operator_name: str,
    auth_method: str,
    scenario: str,
) -> tuple[str, str]:
    if not operator_name.strip():
        return "❌ Operator name required.", ""

    verified, score = SCENARIOS[scenario]
    method_detail = AUTH_METHODS[auth_method]

    operator_id = "op-" + uuid.uuid4().hex[:8]
    state.operator = OperatorSession(
        operator_id=operator_id,
        name=operator_name.strip(),
        verified=verified,
        trust_score=score,
        auth_method=auth_method,
        timestamp=time.time(),
    )

    # Build biometric breakdown
    typing_score  = round(score * random.uniform(0.92, 1.05), 3)
    mouse_score   = round(score * random.uniform(0.88, 1.08), 3)
    scroll_score  = round(score * random.uniform(0.90, 1.06), 3)
    typing_score  = min(typing_score, 1.0)
    mouse_score   = min(mouse_score,  1.0)
    scroll_score  = min(scroll_score, 1.0)

    status = "✅ VERIFIED" if verified else "❌ REJECTED"
    colour = "green" if verified else "red"

    state.log_pipeline(
        "SafePulse auth",
        f"{'PASS' if verified else 'FAIL'} score={score:.2f} op={operator_id}",
    )

    result_md = f"""
## SafePulse Result: <span style='color:{colour}'>{status}</span>

| Metric | Value |
|---|---|
| **Operator** | {operator_name} (`{operator_id}`) |
| **Auth method** | {auth_method} |
| **Method detail** | {method_detail} |
| **Overall trust score** | **{score:.2f}** |
| **Keystroke dynamics** | {typing_score:.3f} |
| **Mouse dynamics** | {mouse_score:.3f} |
| **Scroll behaviour** | {scroll_score:.3f} |
| **Decision** | {status} |
"""

    next_step = (
        "Proceed to **TrustRegistry** to issue an agent certificate."
        if verified else
        "⚠️ Authentication failed. The pipeline is blocked — no agent session can start."
    )
    return result_md, next_step


def build_safepulse_tab(state: SandboxState) -> None:
    gr.Markdown("""
## SafePulse — Operator Biometric Authentication (Simulated)

SafePulse verifies *WHO* is operating the system before any agent is allowed to run.
This sandbox simulates the full verification flow without the real service.
""")

    with gr.Row():
        with gr.Column():
            operator_name = gr.Textbox(
                label="Operator name",
                placeholder="e.g. Alice Smith",
            )
            auth_method = gr.Dropdown(
                label="Authentication method",
                choices=list(AUTH_METHODS.keys()),
                value="Combined (all three)",
            )
            scenario = gr.Dropdown(
                label="Simulation scenario",
                choices=list(SCENARIOS.keys()),
                value="Normal operator — all checks pass",
            )
            auth_btn = gr.Button("🔐 Authenticate", variant="primary")

        with gr.Column():
            result   = gr.Markdown(label="Result")
            next_md  = gr.Markdown()

    auth_btn.click(
        fn=lambda *args: _simulate_auth(state, *args),
        inputs=[operator_name, auth_method, scenario],
        outputs=[result, next_md],
    )
