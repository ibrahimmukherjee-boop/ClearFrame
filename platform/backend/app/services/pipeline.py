"""Full pipeline orchestration."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from app.services import agents as agents_svc
from app.services import safepulse as safepulse_svc
from app.services import trust as trust_svc
from app.services import sessions as sessions_svc
from app.services import sonar as sonar_svc
from app.database import get_conn


def get_pipeline_log() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT message FROM pipeline_log ORDER BY id").fetchall()
    return [r["message"] for r in rows]


def run_full_pipeline() -> dict[str, Any]:
    import asyncio
    return asyncio.run(_run_full_pipeline_async())


async def _run_full_pipeline_async() -> dict[str, Any]:
    steps = []

    if not agents_svc.get_current_agent():
        preset = agents_svc.PRESETS["Customer Support Bot"]
        agents_svc.save_agent({**preset, "owner": "Pipeline Auto"})
    steps.append({"id": "builder", "status": "complete"})

    safepulse_svc.enroll([120.0, 95.0, 110.0, 88.0, 102.0])
    safepulse_svc.verify([118.0, 97.0, 108.0, 90.0, 100.0])
    steps.append({"id": "safepulse", "status": "complete"})

    result = trust_svc.issue_certificate("STANDARD", 24)
    if not result["ok"]:
        return {"ok": False, "message": result["message"], "steps": steps}
    steps.append({"id": "trustregistry", "status": "complete"})

    session_result = await sessions_svc.start_session()
    if not session_result["ok"]:
        return {"ok": False, "message": session_result["message"], "steps": steps}
    steps.extend([
        {"id": "clearframe", "status": "complete"},
        {"id": "aegis", "status": "complete"},
        {"id": "sonar", "status": "complete"},
    ])

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pipeline_log (message, created_at) VALUES (?, ?)",
            ("[pipeline] Full pipeline completed successfully", time.time()),
        )
    return {"ok": True, "message": "Full pipeline executed successfully", "steps": steps, "pipelineLog": get_pipeline_log()}


def reset_all() -> None:
    with get_conn() as conn:
        for table in ["operators", "certificates", "sessions", "tool_calls", "threat_events", "pipeline_log"]:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("UPDATE agents SET is_current = 0")
    sonar_svc.seed_defaults()
