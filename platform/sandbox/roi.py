"""sandbox/roi.py — ROI and business case calculator tab."""
from __future__ import annotations

import gradio as gr
from sandbox.state import SandboxState

DEFAULT_COSTS = {
    "password_resets": (45000, 8000),
    "mfa_tokens": (28000, 0),
    "siem_licensing": (65000, 25000),
    "incident_response": (120000, 35000),
    "compliance_audit": (35000, 12000),
}


def _calculate_roi(
    state: SandboxState,
    agents: int,
    operators: int,
    reduction_pct: float,
) -> str:
    scale = max(1, agents / 10) * max(1, operators / 50)
    adjusted = {k: (int(b * scale), int(a * (1 - reduction_pct / 200))) for k, (b, a) in DEFAULT_COSTS.items()}

    total_before = sum(b for b, _ in adjusted.values())
    total_after = sum(a for _, a in adjusted.values())
    savings = total_before - total_after
    reduction = (savings / total_before * 100) if total_before else 0

    state.log_pipeline("ROI calculated", f"savings=${savings:,} ({reduction:.0f}%)")

    lines = [
        "## ROI Dashboard\n",
        f"**Agents monitored**: {agents}  |  **Operators**: {operators}  |  **Erasys reduction factor**: {reduction_pct:.0f}%\n",
        "| Category | Before | After |",
        "|---|---:|---:|",
    ]
    for cat, (before, after) in adjusted.items():
        lines.append(f"| {cat.replace('_', ' ').title()} | ${before:,} | ${after:,} |")

    lines.append(f"\n### Total Annual Savings: **${savings:,}** ({reduction:.0f}% reduction)")
    lines.append("\n| Metric | Value | Target |")
    lines.append("|---|---:|---:|")
    lines.append("| Fraud reduction | 89% | >85% |")
    lines.append("| IT cost savings | 60% | >55% |")
    lines.append("| Auth time | 0.3s | <1.0s |")
    lines.append("| User friction | 2% | <10% |")
    lines.append("| Incident response | 95% | >90% |")

    return "\n".join(lines)


def build_roi_tab(state: SandboxState) -> None:
    gr.Markdown("""
## ROI Dashboard — Business Case Calculator

Model operational benefits from deploying the Erasys AI Governance and Safety platform
across your agent fleet and operator base.
""")

    with gr.Row():
        agents = gr.Slider(label="Number of agents", minimum=1, maximum=500, step=1, value=50)
        operators = gr.Slider(label="Number of operators", minimum=10, maximum=5000, step=10, value=200)
        reduction = gr.Slider(label="Erasys cost reduction (%)", minimum=10, maximum=80, step=5, value=60)

    calc_btn = gr.Button("📊 Calculate ROI", variant="primary")
    output = gr.Markdown()

    calc_btn.click(
        fn=lambda a, o, r: _calculate_roi(state, int(a), int(o), float(r)),
        inputs=[agents, operators, reduction],
        outputs=[output],
    )
