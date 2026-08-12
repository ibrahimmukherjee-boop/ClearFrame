"""Amazon Bedrock Agents / AgentCore adapter.

Imports action groups from a Bedrock Agent (via boto3, optional) or from an
exported action-group JSON, and exposes each action as a ClearFrame tool.
Also exports ClearFrame tools as a Bedrock action-group OpenAPI payload so a
Bedrock agent can call back into a governed ClearFrame runtime.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from clearframe.adapters.base import AdapterError, ToolAdapter, ToolSpec

Dispatcher = Callable[[str, dict[str, Any]], Awaitable[Any]]


class BedrockAdapter(ToolAdapter):
    source = "bedrock"

    def __init__(
        self,
        action_groups: list[dict[str, Any]] | None = None,
        dispatcher: Dispatcher | None = None,
        agent_id: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        """
        Either pass `action_groups` (exported JSON) + `dispatcher`, or an
        `agent_id` to fetch action groups live via boto3.
        """
        self._groups = action_groups or []
        self._dispatch = dispatcher
        if agent_id is not None:
            self._groups = self._fetch_action_groups(agent_id, region)

    @staticmethod
    def _fetch_action_groups(agent_id: str, region: str) -> list[dict[str, Any]]:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise AdapterError("Fetching Bedrock agents requires `pip install boto3`.") from exc
        client = boto3.client("bedrock-agent", region_name=region)
        groups = []
        paginator = client.get_paginator("list_agent_action_groups")
        for page in paginator.paginate(agentId=agent_id, agentVersion="DRAFT"):
            for summary in page.get("actionGroupSummaries", []):
                detail = client.get_agent_action_group(
                    agentId=agent_id,
                    agentVersion="DRAFT",
                    actionGroupId=summary["actionGroupId"],
                )
                groups.append(detail.get("agentActionGroup", {}))
        return groups

    def discover(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for group in self._groups:
            schema_str = (group.get("apiSchema") or {}).get("payload", "{}")
            try:
                schema = json.loads(schema_str)
            except json.JSONDecodeError:
                schema = {}
            for path, methods in (schema.get("paths") or {}).items():
                for method, op in methods.items():
                    name = op.get("operationId") or f"{method}_{path}".strip("/").replace("/", "_")
                    props: dict[str, Any] = {}
                    for param in op.get("parameters", []):
                        props[param["name"]] = param.get("schema", {"type": "string"})
                    specs.append(ToolSpec(
                        name=name,
                        description=op.get("description", op.get("summary", "")),
                        parameters={"type": "object", "properties": props},
                        source=self.source,
                        fn=self._make_caller(name),
                    ))
        return specs

    def _make_caller(self, name: str):
        if self._dispatch is None:
            async def unbound(**kwargs: Any) -> Any:
                raise AdapterError(
                    f"Bedrock tool '{name}' has no dispatcher. "
                    "Pass dispatcher=... to BedrockAdapter."
                )
            unbound.__name__ = name
            return unbound

        dispatch = self._dispatch

        async def call(**kwargs: Any) -> Any:
            return await dispatch(name, kwargs)
        call.__name__ = name
        return call


def export_action_group(tool_specs: list[ToolSpec], group_name: str = "clearframe") -> dict[str, Any]:
    """Export ClearFrame tools as a Bedrock action-group OpenAPI schema."""
    paths: dict[str, Any] = {}
    for spec in tool_specs:
        paths[f"/{spec.name}"] = {
            "post": {
                "operationId": spec.name,
                "description": spec.description,
                "requestBody": {
                    "content": {"application/json": {"schema": spec.parameters or {"type": "object"}}}
                },
                "responses": {"200": {"description": "Tool result"}},
            }
        }
    return {
        "actionGroupName": group_name,
        "apiSchema": {
            "payload": json.dumps({
                "openapi": "3.0.0",
                "info": {"title": f"ClearFrame tools — {group_name}", "version": "1.0.0"},
                "paths": paths,
            })
        },
    }
