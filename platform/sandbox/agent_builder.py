"""sandbox/agent_builder.py — ClearFrame Agent Builder tab."""
from __future__ import annotations
import json
import uuid
import gradio as gr
from sandbox.state import SandboxState, AgentConfig

PRESETS = {
    "Customer Support Bot": {
        "description": "Handles customer queries, checks order status, escalates complaints.",
        "capabilities": ["web_search", "database_read", "email_send"],
        "model": "llama3",
        "max_steps": 8,
        "allow_web": True, "allow_fs": False, "allow_exec": False,
    },
    "Data Analysis Agent": {
        "description": "Reads internal datasets, produces reports and insights.",
        "capabilities": ["database_read", "file_read", "chart_generate"],
        "model": "mistral",
        "max_steps": 15,
        "allow_web": False, "allow_fs": True, "allow_exec": False,
    },
    "DevOps Automation Agent": {
        "description": "Monitors CI/CD pipelines, auto-triages alerts, opens PRs.",
        "capabilities": ["git_read", "git_write", "shell_exec", "webhook_send"],
        "model": "codellama",
        "max_steps": 20,
        "allow_web": True, "allow_fs": True, "allow_exec": True,
    },
    "Research Assistant": {
        "description": "Searches the web, summarises papers, drafts reports.",
        "capabilities": ["web_search", "file_write", "pdf_read"],
        "model": "llama3",
        "max_steps": 12,
        "allow_web": True, "allow_fs": True, "allow_exec": False,
    },
}

ALL_CAPABILITIES = [
    "web_search", "database_read", "database_write",
    "file_read", "file_write", "email_send",
    "chart_generate", "pdf_read", "git_read",
    "git_write", "shell_exec", "webhook_send",
]


def _apply_preset(preset_name: str):
    p = PRESETS.get(preset_name)
    if not p:
        return "", "", [], "llama3", 10, False, False, False
    return (
        preset_name,
        p["description"],
        p["capabilities"],
        p["model"],
        p["max_steps"],
        p["allow_web"],
        p["allow_fs"],
        p["allow_exec"],
    )


def _save_agent(
    state: SandboxState,
    name, description, capabilities, model,
    max_steps, allow_web, allow_fs, allow_exec,
) -> str:
    if not name.strip():
        return "❌ Agent name is required."

    agent_id = state.new_agent_id()
    state.agent = AgentConfig(
        agent_id=agent_id,
        name=name.strip(),
        description=description.strip(),
        capabilities=list(capabilities),
        provider="ollama",
        model=model,
        max_steps=int(max_steps),
        allow_web=allow_web,
        allow_fs=allow_fs,
        allow_exec=allow_exec,
    )
    state.log_pipeline("Agent defined", f"{name} ({agent_id})")

    caps = ", ".join(capabilities) or "(none)"
    flags = []
    if allow_web:  flags.append("web")
    if allow_fs:   flags.append("filesystem")
    if allow_exec: flags.append("exec")

    return f"""✅ Agent saved.

**ID**: `{agent_id}`
**Name**: {name}
**Model**: {model} (max {max_steps} steps)
**Capabilities**: {caps}
**Elevated permissions**: {', '.join(flags) or 'none'}

Proceed to **SafePulse** to authenticate as an operator, then issue a **TrustRegistry** certificate.
"""


def build_agent_builder_tab(state: SandboxState) -> None:
    gr.Markdown("## Agent Builder\nDefine your ClearFrame agent — name, capabilities, model, and permission scopes.")

    with gr.Row():
        with gr.Column(scale=2):
            preset = gr.Dropdown(
                label="Load a preset",
                choices=list(PRESETS.keys()),
                value=None,
            )
            name = gr.Textbox(label="Agent name", placeholder="e.g. my-support-agent")
            description = gr.Textbox(
                label="Description / goal",
                placeholder="What should this agent do?",
                lines=3,
            )
            capabilities = gr.CheckboxGroup(
                label="Capabilities (define allowed tools)",
                choices=ALL_CAPABILITIES,
                value=[],
            )

        with gr.Column(scale=1):
            model = gr.Dropdown(
                label="LLM provider / model",
                choices=["llama3", "mistral", "codellama", "qwen2", "gemma2"],
                value="llama3",
            )
            max_steps = gr.Slider(label="Max steps", minimum=1, maximum=50, step=1, value=10)
            allow_web  = gr.Checkbox(label="Allow web access",    value=False)
            allow_fs   = gr.Checkbox(label="Allow filesystem access", value=False)
            allow_exec = gr.Checkbox(label="Allow shell execution",   value=False)

    save_btn = gr.Button("Save Agent →", variant="primary")
    result   = gr.Markdown()

    preset.change(
        fn=_apply_preset,
        inputs=[preset],
        outputs=[name, description, capabilities, model, max_steps, allow_web, allow_fs, allow_exec],
    )

    save_btn.click(
        fn=lambda *args: _save_agent(state, *args),
        inputs=[name, description, capabilities, model, max_steps, allow_web, allow_fs, allow_exec],
        outputs=[result],
    )
