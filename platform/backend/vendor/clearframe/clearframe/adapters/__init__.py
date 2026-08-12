"""ClearFrame adapters — connect any agent toolchain to the ClearFrame runtime.

Every adapter converts external tools into plain async callables that can be
registered in an AgentSession tool registry, and (where the ecosystem supports
it) exports ClearFrame tools back out. Supported ecosystems:

  - MCP (Model Context Protocol)      → MCPAdapter (stdio + HTTP)
  - LangChain / LangGraph             → LangChainAdapter
  - OpenAI tools / Agents SDK, Azure  → OpenAIToolsAdapter
  - Amazon Bedrock Agents / AgentCore → BedrockAdapter
  - NVIDIA NIM / IBM watsonx / REST   → HTTPToolAdapter (OpenAPI-style)
  - Google A2A                        → AgentCard export (a2a_card)
"""

from clearframe.adapters.base import AdapterError, ToolAdapter, ToolSpec
from clearframe.adapters.http_adapter import HTTPToolAdapter
from clearframe.adapters.mcp_adapter import MCPAdapter
from clearframe.adapters.openai_adapter import OpenAIToolsAdapter
from clearframe.adapters.langchain_adapter import LangChainAdapter
from clearframe.adapters.bedrock_adapter import BedrockAdapter
from clearframe.adapters.a2a import a2a_card

__all__ = [
    "AdapterError",
    "ToolAdapter",
    "ToolSpec",
    "MCPAdapter",
    "LangChainAdapter",
    "OpenAIToolsAdapter",
    "BedrockAdapter",
    "HTTPToolAdapter",
    "a2a_card",
]
