"""OpenTelemetry-compatible export for traces, metrics, and audit spans.

Emits OTEL-shaped JSON lines (compatible with collectors that accept JSON)
so ClearFrame matches AgentCore-style observability without AWS lock-in.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from app.config import DATA_DIR

OTEL_ENABLED = os.environ.get("CLEARFRAME_OTEL", "true").lower() in {"1", "true", "yes"}
OTEL_PATH = os.environ.get("CLEARFRAME_OTEL_PATH", str(DATA_DIR / "otel.jsonl"))


def emit_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    status: str = "OK",
    duration_ms: float = 0.0,
) -> dict[str, Any]:
    span = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "clearframe-api"}}]},
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": uuid.uuid4().hex,
                                "spanId": uuid.uuid4().hex[:16],
                                "name": name,
                                "kind": 1,
                                "startTimeUnixNano": str(int(time.time() * 1e9)),
                                "endTimeUnixNano": str(int((time.time() + duration_ms / 1000) * 1e9)),
                                "attributes": [
                                    {"key": k, "value": {"stringValue": str(v)}}
                                    for k, v in (attributes or {}).items()
                                ],
                                "status": {"code": 1 if status == "OK" else 2, "message": status},
                            }
                        ]
                    }
                ],
            }
        ]
    }
    if OTEL_ENABLED:
        try:
            with open(OTEL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(span) + "\n")
        except Exception:
            pass
    return span


def emit_metric(name: str, value: float, labels: dict[str, str] | None = None) -> dict[str, Any]:
    metric = {
        "name": name,
        "value": value,
        "labels": labels or {},
        "timestamp": time.time(),
        "service": "clearframe-api",
    }
    if OTEL_ENABLED:
        try:
            with open(OTEL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"metric": metric}) + "\n")
        except Exception:
            pass
    return metric
