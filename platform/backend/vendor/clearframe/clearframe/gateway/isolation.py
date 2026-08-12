"""
ClearFrame Reader/Actor Isolation

The single biggest architectural improvement over OpenClaw and MCP.

OpenClaw runs one process that fetches untrusted content AND executes
tool calls — making indirect prompt injection structurally unavoidable.

ClearFrame separates:
  READER  — reads untrusted content only. No tool execution.
  ACTOR   — executes tool calls only. Never reads untrusted content.

All communication crosses a typed, schema-validated MessagePipe.
Raw strings from untrusted sources never reach the Actor.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel


class PipeMessageType(str, Enum):
    CONTENT_CHUNK  = "content_chunk"
    CONTENT_DONE   = "content_done"
    TOOL_CALL_SPEC = "tool_call_spec"
    TOOL_RESULT    = "tool_result"
    TOOL_ERROR     = "tool_error"


class PipeMessage(BaseModel):
    msg_type: PipeMessageType
    session_id: str
    payload: dict[str, Any]

    def serialise(self) -> bytes:
        return (self.model_dump_json() + "\n").encode()

    @classmethod
    def deserialise(cls, data: bytes) -> "PipeMessage":
        return cls.model_validate_json(data.decode().strip())


class MessagePipe:
    """Async in-process typed message pipe between Reader and Actor."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[PipeMessage] = asyncio.Queue(maxsize=256)

    async def send(self, msg: PipeMessage) -> None:
        await self._queue.put(msg)

    async def recv(self) -> PipeMessage:
        return await self._queue.get()

    async def recv_with_timeout(self, timeout: float) -> PipeMessage | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


class ReaderSandbox:
    """
    Isolated Reader process.
    Reads untrusted content. NEVER executes tool calls.
    Sends typed ContentChunk messages through the pipe only.
    """

    def __init__(self, session_id: str, pipe: MessagePipe) -> None:
        self._session_id = session_id
        self._pipe = pipe

    async def ingest_text(self, content: str, source: str) -> None:
        await self._pipe.send(PipeMessage(
            msg_type=PipeMessageType.CONTENT_CHUNK,
            session_id=self._session_id,
            payload={"content": content, "source": source, "length": len(content)},
        ))

    async def signal_done(self) -> None:
        await self._pipe.send(PipeMessage(
            msg_type=PipeMessageType.CONTENT_DONE,
            session_id=self._session_id,
            payload={},
        ))


class ActorSandbox:
    """
    Isolated Actor process.
    Executes approved tool calls. NEVER reads untrusted content directly.
    Receives only validated ToolCallSpec messages from the Goal Monitor.
    """

    def __init__(self, session_id: str, pipe: MessagePipe, tool_registry: dict[str, Callable]) -> None:
        self._session_id = session_id
        self._pipe = pipe
        self._tools = tool_registry

    async def execute_approved_call(self, tool_name: str, args: dict[str, Any]) -> Any:
        tool_fn = self._tools.get(tool_name)
        if tool_fn is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        if asyncio.iscoroutinefunction(tool_fn):
            result = await tool_fn(**args)
        else:
            result = tool_fn(**args)
        await self._pipe.send(PipeMessage(
            msg_type=PipeMessageType.TOOL_RESULT,
            session_id=self._session_id,
            payload={"tool_name": tool_name, "result": str(result)},
        ))
        return result
