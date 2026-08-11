from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


class ToolBinding(BaseModel):
    """One tool made available to the agent, from any ecosystem."""

    name: str
    adapter: Literal["native", "mcp", "langchain", "openai", "bedrock", "http"] = "native"
    # Adapter-specific configuration:
    #   mcp:    {"endpoint": "https://..."}
    #   http:   {"url": "...", "method": "POST"}
    #   bedrock:{"agent_id": "...", "region": "..."}
    config: dict[str, Any] = Field(default_factory=dict)
    max_calls_per_session: int | None = None
    require_approval: bool = False


class AgentSpec(BaseModel):
    """Portable, auditable description of a governed agent."""

    schema_version: str = "1.0"
    name: str
    description: str = ""
    goal: str
    provider: str = "ollama"          # ollama | openai | anthropic | bedrock | ...
    model: str = "llama3"
    tools: list[ToolBinding] = Field(default_factory=list)
    policy_packs: list[str] = Field(default_factory=lambda: ["baseline"])
    trust_level: str = "STANDARD"     # requested TrustRegistry level
    allow_file_write: bool = False
    allow_code_execution: bool = False
    max_steps: int = 30
    allowed_domains: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_yaml(self) -> str:
        if yaml is None:
            raise RuntimeError("PyYAML required: pip install pyyaml")
        return yaml.safe_dump(self.model_dump(), sort_keys=False)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in (".yaml", ".yml"):
            path.write_text(self.to_yaml())
        else:
            path.write_text(json.dumps(self.model_dump(), indent=2))
        return path

    # ── Runtime conversion ────────────────────────────────────────────────

    def to_manifest(self):
        """Convert to a runtime GoalManifest."""
        from clearframe.core.manifest import GoalManifest, ResourceScope, ToolPermission

        return GoalManifest(
            goal=self.goal,
            permitted_tools=[
                ToolPermission(
                    tool_name=t.name,
                    max_calls_per_session=t.max_calls_per_session,
                    require_approval=t.require_approval,
                )
                for t in self.tools
            ],
            allow_file_write=self.allow_file_write,
            allow_code_execution=self.allow_code_execution,
            max_steps=self.max_steps,
            resource_scope=ResourceScope(allowed_domains=self.allowed_domains),
        )

    def build_tool_registry(self) -> dict[str, Any]:
        """Resolve every ToolBinding into a callable via its adapter."""
        registry: dict[str, Any] = {}
        mcp_cache: dict[str, Any] = {}
        for binding in self.tools:
            if binding.adapter == "mcp":
                from clearframe.adapters.mcp_adapter import MCPAdapter

                endpoint = binding.config["endpoint"]
                if endpoint not in mcp_cache:
                    mcp_cache[endpoint] = MCPAdapter(
                        endpoint, headers=binding.config.get("headers")
                    ).as_tool_registry()
                if binding.name in mcp_cache[endpoint]:
                    registry[binding.name] = mcp_cache[endpoint][binding.name]
            elif binding.adapter == "http":
                from clearframe.adapters.http_adapter import HTTPTool, HTTPToolAdapter

                tool = HTTPTool(
                    name=binding.name,
                    url=binding.config["url"],
                    method=binding.config.get("method", "POST"),
                    description=binding.config.get("description", ""),
                    headers=binding.config.get("headers", {}),
                )
                registry.update(HTTPToolAdapter([tool]).as_tool_registry())
            # native / langchain / openai / bedrock bindings are attached in
            # code because they need live objects (a dispatcher or instances).
        return registry


def load_spec(path: str | Path) -> AgentSpec:
    path = Path(path)
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise RuntimeError("PyYAML required: pip install pyyaml")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return AgentSpec.model_validate(data)


TEMPLATE = AgentSpec(
    name="my-agent",
    description="Example governed agent",
    goal="Answer customer support questions accurately and politely",
    provider="ollama",
    model="llama3",
    tools=[
        ToolBinding(name="web_search", adapter="native", max_calls_per_session=10),
        ToolBinding(
            name="send_email",
            adapter="native",
            max_calls_per_session=1,
            require_approval=True,
        ),
    ],
    policy_packs=["baseline", "owasp-llm"],
    allowed_domains=["*.example.com"],
)
