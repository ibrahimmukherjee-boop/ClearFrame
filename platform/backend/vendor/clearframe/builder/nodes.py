"""Node definitions for the ClearFrame drag-and-drop agent builder.

Every node type that can appear on the canvas is registered here.
Nodes are the building blocks of an AgentGraph; edges connect them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class NodeKind(str, Enum):
    # ---- LLM providers ----
    LLM_OPENAI = "llm_openai"
    LLM_ANTHROPIC = "llm_anthropic"
    LLM_GEMINI = "llm_gemini"
    LLM_MISTRAL = "llm_mistral"
    LLM_OLLAMA = "llm_ollama"
    LLM_HUGGINGFACE = "llm_huggingface"

    # ---- Memory / state ----
    MEMORY_BUFFER = "memory_buffer"
    MEMORY_VECTOR = "memory_vector"
    MEMORY_REDIS = "memory_redis"

    # ---- Tools / integrations ----
    TOOL_WEB_SEARCH = "tool_web_search"
    TOOL_CODE_EXEC = "tool_code_exec"
    TOOL_REST_API = "tool_rest_api"
    TOOL_SQL = "tool_sql"
    TOOL_FILE = "tool_file"
    TOOL_EMAIL = "tool_email"
    TOOL_CALENDAR = "tool_calendar"
    TOOL_SLACK = "tool_slack"
    TOOL_GITHUB = "tool_github"
    TOOL_SONAR = "tool_sonar"        # Erasys Sonar security layer

    # ---- Flow control ----
    ROUTER = "router"
    BRANCH = "branch"
    LOOP = "loop"
    AGGREGATOR = "aggregator"

    # ---- I/O ----
    INPUT = "input"
    OUTPUT = "output"
    HUMAN_IN_LOOP = "human_in_loop"  # Aegis HITL gate

    # ---- Monitoring ----
    CLEARFRAME_GOAL = "clearframe_goal"  # Goal tracker for ClearFrame
    PROMPT_TEMPLATE = "prompt_template"


@dataclass
class PortSpec:
    """Describes an input or output port on a node."""
    name: str
    data_type: str = "any"          # e.g. "str", "list", "Message"
    required: bool = True
    description: str = ""


@dataclass
class NodeSpec:
    """Static specification for a node type shown in the palette."""
    kind: NodeKind
    label: str
    category: str
    description: str
    icon: str = "⚙️"
    color: str = "#6366f1"           # Tailwind indigo-500
    inputs: List[PortSpec] = field(default_factory=list)
    outputs: List[PortSpec] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    executor: Optional[Callable] = field(default=None, repr=False)


class NodeRegistry:
    """Central registry of all available node types."""

    _registry: Dict[NodeKind, NodeSpec] = {}

    @classmethod
    def register(cls, spec: NodeSpec) -> None:
        cls._registry[spec.kind] = spec

    @classmethod
    def get(cls, kind: NodeKind) -> NodeSpec:
        if kind not in cls._registry:
            raise KeyError(f"Unknown node kind: {kind}")
        return cls._registry[kind]

    @classmethod
    def all_specs(cls) -> List[NodeSpec]:
        return list(cls._registry.values())

    @classmethod
    def by_category(cls) -> Dict[str, List[NodeSpec]]:
        result: Dict[str, List[NodeSpec]] = {}
        for spec in cls._registry.values():
            result.setdefault(spec.category, []).append(spec)
        return result


# ---------------------------------------------------------------------------
# Register all built-in node types
# ---------------------------------------------------------------------------

_BUILTIN_SPECS: List[NodeSpec] = [
    # LLM providers
    NodeSpec(NodeKind.LLM_OPENAI, "OpenAI LLM", "LLM", "Call OpenAI chat completions API",
             "🤖", "#10b981",
             inputs=[PortSpec("prompt", "str"), PortSpec("system", "str", required=False)],
             outputs=[PortSpec("response", "str")],
             config_schema={"model": "gpt-4o", "temperature": 0.7, "api_key_env": "OPENAI_API_KEY"}),
    NodeSpec(NodeKind.LLM_ANTHROPIC, "Anthropic Claude", "LLM", "Call Anthropic Claude API",
             "🤖", "#f59e0b",
             inputs=[PortSpec("prompt", "str"), PortSpec("system", "str", required=False)],
             outputs=[PortSpec("response", "str")],
             config_schema={"model": "claude-3-5-sonnet-20241022", "max_tokens": 4096, "api_key_env": "ANTHROPIC_API_KEY"}),
    NodeSpec(NodeKind.LLM_GEMINI, "Google Gemini", "LLM", "Call Google Gemini API",
             "🤖", "#3b82f6",
             inputs=[PortSpec("prompt", "str")],
             outputs=[PortSpec("response", "str")],
             config_schema={"model": "gemini-1.5-pro", "api_key_env": "GOOGLE_API_KEY"}),
    NodeSpec(NodeKind.LLM_MISTRAL, "Mistral AI", "LLM", "Call Mistral AI API",
             "🤖", "#8b5cf6",
             inputs=[PortSpec("prompt", "str")],
             outputs=[PortSpec("response", "str")],
             config_schema={"model": "mistral-large-latest", "api_key_env": "MISTRAL_API_KEY"}),
    NodeSpec(NodeKind.LLM_OLLAMA, "Ollama (Local)", "LLM", "Run local models via Ollama",
             "🖥️", "#64748b",
             inputs=[PortSpec("prompt", "str")],
             outputs=[PortSpec("response", "str")],
             config_schema={"model": "llama3", "base_url": "http://localhost:11434"}),
    NodeSpec(NodeKind.LLM_HUGGINGFACE, "HuggingFace", "LLM", "Call HuggingFace Inference API",
             "🤗", "#f97316",
             inputs=[PortSpec("prompt", "str")],
             outputs=[PortSpec("response", "str")],
             config_schema={"model": "", "api_key_env": "HF_TOKEN"}),

    # Memory
    NodeSpec(NodeKind.MEMORY_BUFFER, "Buffer Memory", "Memory", "In-process conversation buffer",
             "🧠", "#06b6d4",
             inputs=[PortSpec("message", "str")],
             outputs=[PortSpec("history", "list")],
             config_schema={"max_messages": 20}),
    NodeSpec(NodeKind.MEMORY_VECTOR, "Vector Memory", "Memory", "Semantic search over past context",
             "🔍", "#06b6d4",
             inputs=[PortSpec("query", "str")],
             outputs=[PortSpec("context", "str")],
             config_schema={"collection": "agent_memory", "top_k": 5, "embeddings_model": "text-embedding-3-small"}),
    NodeSpec(NodeKind.MEMORY_REDIS, "Redis Memory", "Memory", "Persistent memory backed by Redis",
             "📦", "#ef4444",
             inputs=[PortSpec("key", "str"), PortSpec("value", "str", required=False)],
             outputs=[PortSpec("value", "str")],
             config_schema={"redis_url_env": "REDIS_URL", "ttl_seconds": 86400}),

    # Tools
    NodeSpec(NodeKind.TOOL_WEB_SEARCH, "Web Search", "Tool", "Search the web via Perplexity/Brave/Google",
             "🌐", "#0ea5e9",
             inputs=[PortSpec("query", "str")],
             outputs=[PortSpec("results", "str")],
             config_schema={"provider": "perplexity", "api_key_env": "SEARCH_API_KEY", "num_results": 5}),
    NodeSpec(NodeKind.TOOL_CODE_EXEC, "Code Executor", "Tool", "Run Python/JS in a sandbox",
             "💻", "#0ea5e9",
             inputs=[PortSpec("code", "str")],
             outputs=[PortSpec("stdout", "str"), PortSpec("stderr", "str")],
             config_schema={"runtime": "python3", "timeout_seconds": 30}),
    NodeSpec(NodeKind.TOOL_REST_API, "REST API Call", "Tool", "Make HTTP requests to any REST API",
             "🔌", "#0ea5e9",
             inputs=[PortSpec("url", "str"), PortSpec("body", "str", required=False)],
             outputs=[PortSpec("response", "str"), PortSpec("status_code", "int")],
             config_schema={"method": "GET", "headers": {}, "auth_env": ""}),
    NodeSpec(NodeKind.TOOL_SQL, "SQL Query", "Tool", "Run SQL against a database",
             "🗄️", "#0ea5e9",
             inputs=[PortSpec("query", "str")],
             outputs=[PortSpec("rows", "list")],
             config_schema={"connection_env": "DATABASE_URL"}),
    NodeSpec(NodeKind.TOOL_SONAR, "Sonar Security", "Tool",
             "Pipe LLM calls through Sonar threat detection before execution",
             "🛡️", "#ef4444",
             inputs=[PortSpec("prompt", "str"), PortSpec("response", "str", required=False)],
             outputs=[PortSpec("safe_prompt", "str"), PortSpec("alerts", "list")],
             config_schema={"sonar_url": "http://sonar:8000", "block_on_critical": True}),

    # Flow control
    NodeSpec(NodeKind.ROUTER, "Router", "Flow", "Route messages based on a condition",
             "🔀", "#a855f7",
             inputs=[PortSpec("input", "str"), PortSpec("condition", "str")],
             outputs=[PortSpec("true_branch", "str"), PortSpec("false_branch", "str")],
             config_schema={"condition_type": "python_expr"}),
    NodeSpec(NodeKind.LOOP, "Loop", "Flow", "Repeat a sub-graph up to N times",
             "🔁", "#a855f7",
             inputs=[PortSpec("input", "any")],
             outputs=[PortSpec("output", "any")],
             config_schema={"max_iterations": 5, "exit_condition": ""}),
    NodeSpec(NodeKind.HUMAN_IN_LOOP, "Human-in-the-Loop (Aegis)", "Flow",
             "Pause execution and request human approval via Aegis HITL",
             "👤", "#f59e0b",
             inputs=[PortSpec("payload", "any")],
             outputs=[PortSpec("approved", "any"), PortSpec("rejected", "any")],
             config_schema={"aegis_url": "http://aegis:8000", "timeout_seconds": 3600}),

    # I/O
    NodeSpec(NodeKind.INPUT, "Input", "I/O", "Entry point for the agent graph",
             "📥", "#22c55e",
             inputs=[],
             outputs=[PortSpec("data", "any")],
             config_schema={"input_type": "text"}),
    NodeSpec(NodeKind.OUTPUT, "Output", "I/O", "Exit point — emits the final result",
             "📤", "#22c55e",
             inputs=[PortSpec("data", "any")],
             outputs=[],
             config_schema={"output_format": "text"}),

    # Monitoring
    NodeSpec(NodeKind.CLEARFRAME_GOAL, "Goal Monitor", "Monitoring",
             "Tracks whether the agent is progressing towards its declared goal",
             "🎯", "#ec4899",
             inputs=[PortSpec("state", "any")],
             outputs=[PortSpec("on_track", "bool"), PortSpec("deviation_report", "str")],
             config_schema={"goal_description": "", "evaluation_model": "gpt-4o-mini"}),
    NodeSpec(NodeKind.PROMPT_TEMPLATE, "Prompt Template", "Monitoring",
             "Jinja2-style prompt template with variable interpolation",
             "📝", "#ec4899",
             inputs=[PortSpec("variables", "dict")],
             outputs=[PortSpec("rendered_prompt", "str")],
             config_schema={"template": "", "template_id": ""}),
]

for _spec in _BUILTIN_SPECS:
    NodeRegistry.register(_spec)
