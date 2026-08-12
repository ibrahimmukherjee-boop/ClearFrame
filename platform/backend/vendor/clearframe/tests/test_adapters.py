"""Tests for adapters and agent specs."""

import asyncio

import pytest

from clearframe.adapters import OpenAIToolsAdapter, a2a_card
from clearframe.adapters.base import ToolSpec
from clearframe.adapters.openai_adapter import export
from clearframe.agents import AgentSpec, TEMPLATE, ToolBinding, load_spec


def test_openai_adapter_roundtrip():
    calls = []

    async def dispatcher(name, args):
        calls.append((name, args))
        return "ok"

    defs = [{
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Look something up",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
    }]
    adapter = OpenAIToolsAdapter(defs, dispatcher)
    registry = adapter.as_tool_registry()
    assert "lookup" in registry
    result = asyncio.run(registry["lookup"](q="test"))
    assert result == "ok"
    assert calls == [("lookup", {"q": "test"})]


def test_toolspec_openai_export():
    spec = ToolSpec(name="t", description="d", parameters={"type": "object"})
    exported = export([spec])
    assert exported[0]["function"]["name"] == "t"


def test_a2a_card_shape():
    card = a2a_card(name="x", description="d", url="https://x.example")
    assert card["protocolVersion"] == "1.0"
    assert card["metadata"]["governance"]["policy_engine"] is True


def test_agent_spec_yaml_roundtrip(tmp_path):
    path = TEMPLATE.save(tmp_path / "demo.agent.yaml")
    spec = load_spec(path)
    assert spec.name == TEMPLATE.name
    assert spec.policy_packs == ["baseline", "owasp-llm"]


def test_agent_spec_to_manifest():
    manifest = TEMPLATE.to_manifest()
    assert manifest.goal == TEMPLATE.goal
    names = [p.tool_name for p in manifest.permitted_tools]
    assert "web_search" in names and "send_email" in names


def test_spec_requires_goal():
    with pytest.raises(Exception):
        AgentSpec.model_validate({"name": "x"})  # goal missing


def test_tool_binding_defaults():
    binding = ToolBinding(name="t")
    assert binding.adapter == "native"
    assert binding.require_approval is False
