"""Multi-agent workflow orchestration."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import agents as agents_svc
from app.services import llm_agent as llm_svc


def init_workflows_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                steps TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT,
                results TEXT,
                started_at REAL,
                completed_at REAL
            );
            """
        )


def list_workflows() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
    return [
        {
            "workflowId": r["workflow_id"], "name": r["name"], "description": r["description"] or "",
            "steps": json.loads(r["steps"]), "status": r["status"],
        }
        for r in rows
    ]


def create_workflow(name: str, description: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    wid = f"wf-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO workflows (workflow_id, name, description, steps, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
            (wid, name, description, json.dumps(steps), time.time()),
        )
    return {"workflowId": wid, "name": name, "steps": steps}


async def run_workflow(workflow_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)).fetchone()
    if not row:
        return {"ok": False, "message": "Workflow not found"}

    steps = json.loads(row["steps"])
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    results: list[dict[str, Any]] = []
    started = time.time()

    for i, step in enumerate(steps):
        agent_id = step.get("agentId")
        goal = step.get("goal", step.get("task", ""))
        agent = None
        if agent_id:
            for a in agents_svc.list_agents():
                if a["agentId"] == agent_id:
                    agent = a
                    break
        if not agent:
            agent = agents_svc.get_current_agent()
        if not agent:
            return {"ok": False, "message": f"No agent for step {i + 1}"}

        agents_svc.set_current_agent(agent["agentId"])
        result = await llm_svc.run_agent_loop(agent, goal, max_steps=step.get("maxSteps", 5))
        results.append({"step": i + 1, "agentId": agent["agentId"], "goal": goal, "result": result})

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO workflow_runs (run_id, workflow_id, status, results, started_at, completed_at) VALUES (?, ?, 'completed', ?, ?, ?)",
            (run_id, workflow_id, json.dumps(results, default=str), started, time.time()),
        )
    return {"ok": True, "runId": run_id, "results": results}
