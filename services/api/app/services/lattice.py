"""Lattice — ClearFrame elastic agent execution scale-out (open source).

Self-hosted worker pool for concurrent agent sessions. No cloud lock-in:
operators scale Lattice workers up/down; jobs queue and drain across the pool.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc

_DEFAULT_WORKERS = int(os.environ.get("CLEARFRAME_LATTICE_WORKERS", "4"))
_MAX_WORKERS = int(os.environ.get("CLEARFRAME_LATTICE_MAX_WORKERS", "32"))
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_worker_count = _DEFAULT_WORKERS


def init_lattice_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lattice_jobs (
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT,
                agent_id TEXT,
                goal TEXT,
                status TEXT,
                worker_id TEXT,
                result TEXT,
                error TEXT,
                created_at REAL,
                started_at REAL,
                finished_at REAL
            );
            CREATE TABLE IF NOT EXISTS lattice_workers (
                worker_id TEXT PRIMARY KEY,
                status TEXT,
                capacity INTEGER,
                jobs_done INTEGER DEFAULT 0,
                created_at REAL,
                last_heartbeat REAL
            );
            """
        )
    ensure_pool(_DEFAULT_WORKERS)


def ensure_pool(n: int) -> dict[str, Any]:
    global _executor, _worker_count
    n = max(1, min(int(n), _MAX_WORKERS))
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=False)
        _executor = ThreadPoolExecutor(max_workers=n, thread_name_prefix="lattice")
        _worker_count = n
        now = time.time()
        with get_conn() as conn:
            conn.execute("DELETE FROM lattice_workers")
            for i in range(n):
                wid = f"lw-{i + 1}"
                conn.execute(
                    "INSERT INTO lattice_workers (worker_id, status, capacity, jobs_done, created_at, last_heartbeat) VALUES (?, 'ready', 1, 0, ?, ?)",
                    (wid, now, now),
                )
    return status()


def status() -> dict[str, Any]:
    with get_conn() as conn:
        workers = conn.execute("SELECT * FROM lattice_workers ORDER BY worker_id").fetchall()
        queued = conn.execute("SELECT COUNT(*) AS c FROM lattice_jobs WHERE status = 'queued'").fetchone()["c"]
        running = conn.execute("SELECT COUNT(*) AS c FROM lattice_jobs WHERE status = 'running'").fetchone()["c"]
        done = conn.execute("SELECT COUNT(*) AS c FROM lattice_jobs WHERE status = 'completed'").fetchone()["c"]
        failed = conn.execute("SELECT COUNT(*) AS c FROM lattice_jobs WHERE status = 'failed'").fetchone()["c"]
    return {
        "product": "Lattice",
        "openSource": True,
        "workers": _worker_count,
        "maxWorkers": _MAX_WORKERS,
        "queued": queued,
        "running": running,
        "completed": done,
        "failed": failed,
        "pool": [
            {
                "workerId": w["worker_id"],
                "status": w["status"],
                "jobsDone": w["jobs_done"],
                "lastHeartbeat": w["last_heartbeat"],
            }
            for w in workers
        ],
    }


def scale(workers: int) -> dict[str, Any]:
    result = ensure_pool(workers)
    audit_svc.write_event("lattice_scale", f"workers-{workers}", {"workers": workers})
    return result


def enqueue(agent_id: str, goal: str, tenant_id: str = "default") -> dict[str, Any]:
    job_id = f"lj-{uuid.uuid4().hex[:10]}"
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lattice_jobs (job_id, tenant_id, agent_id, goal, status, created_at) VALUES (?, ?, ?, ?, 'queued', ?)",
            (job_id, tenant_id, agent_id, goal[:2000], now),
        )
    _dispatch(job_id)
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM lattice_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not r:
        return {}
    return {
        "jobId": r["job_id"],
        "tenantId": r["tenant_id"],
        "agentId": r["agent_id"],
        "goal": r["goal"],
        "status": r["status"],
        "workerId": r["worker_id"],
        "result": json.loads(r["result"]) if r["result"] else None,
        "error": r["error"],
        "createdAt": r["created_at"],
        "startedAt": r["started_at"],
        "finishedAt": r["finished_at"],
    }


def list_jobs(limit: int = 30) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT job_id FROM lattice_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [get_job(r["job_id"]) for r in rows]


def _dispatch(job_id: str) -> None:
    global _executor
    if _executor is None:
        ensure_pool(_worker_count)
    assert _executor is not None
    _executor.submit(_run_job, job_id)


def _run_job(job_id: str) -> None:
    now = time.time()
    worker_id = f"lw-{(hash(job_id) % max(_worker_count, 1)) + 1}"
    with get_conn() as conn:
        conn.execute(
            "UPDATE lattice_jobs SET status='running', worker_id=?, started_at=? WHERE job_id=?",
            (worker_id, now, job_id),
        )
        conn.execute(
            "UPDATE lattice_workers SET status='busy', last_heartbeat=? WHERE worker_id=?",
            (now, worker_id),
        )
    try:
        job = get_job(job_id)
        # Governed worker execution: Continuum memory + policy-gated tool plan + optional Sonar scan
        from app.services import memory as continuum
        from app.services import agents as agents_svc
        from app.services import policy as policy_svc
        from app.services import sonar as sonar_svc

        agent = agents_svc.get_agent(job.get("agentId") or "") or {"agentId": job.get("agentId"), "name": "unknown"}
        goal = job.get("goal") or ""
        continuum.put(
            tenant_id=job.get("tenantId") or "default",
            agent_id=agent.get("agentId") or "unknown",
            content=f"Lattice job {job_id}: {goal[:200]}",
            strategy="episodic",
            namespace="lattice",
            session_id=job_id,
            tags=["lattice", "scale"],
        )

        # Policy gate sample tool implied by goal
        tool = "web_search"
        if any(tok in goal.lower() for tok in ("shell", "exec", "rm ", "drop")):
            tool = "shell_exec"
        elif any(tok in goal.lower() for tok in ("file", "read", "write")):
            tool = "file_read"
        decision = policy_svc.evaluate(
            tool,
            {"goal": goal[:120]},
            {"agentId": agent.get("agentId"), "capabilities": agent.get("capabilities") or []},
        )
        sonar = sonar_svc.scan_prompt(goal[:240], agent_name=agent.get("name") or "lattice-worker")

        result = {
            "ok": True,
            "runtime": "lattice",
            "agentId": agent.get("agentId"),
            "goal": goal,
            "policy": decision,
            "sonar": {
                "type": sonar.get("type"),
                "severity": sonar.get("severity"),
                "blocked": sonar.get("blocked"),
                "contained": bool((sonar.get("containment") or {}).get("ok")),
            },
            "message": "Job completed on Lattice worker pool with policy + Sonar gates",
        }
        with get_conn() as conn:
            conn.execute(
                "UPDATE lattice_jobs SET status='completed', result=?, finished_at=? WHERE job_id=?",
                (json.dumps(result), time.time(), job_id),
            )
            conn.execute(
                "UPDATE lattice_workers SET status='ready', jobs_done=jobs_done+1, last_heartbeat=? WHERE worker_id=?",
                (time.time(), worker_id),
            )
    except Exception as exc:
        with get_conn() as conn:
            conn.execute(
                "UPDATE lattice_jobs SET status='failed', error=?, finished_at=? WHERE job_id=?",
                (str(exc)[:500], time.time(), job_id),
            )
            conn.execute(
                "UPDATE lattice_workers SET status='ready', last_heartbeat=? WHERE worker_id=?",
                (time.time(), worker_id),
            )
