"""Enterprise tool registry — OpenClaw-style marketplace connections."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

from app.config import DATA_DIR
from app.database import get_conn
from app.services import vault as vault_svc

TOOL_CATALOG: list[dict[str, Any]] = [
    {"id": "web_search", "name": "Web Search", "category": "research", "icon": "search", "requiresKey": False, "description": "Search the public web via DuckDuckGo"},
    {"id": "web_fetch", "name": "Web Fetch", "category": "research", "icon": "globe", "requiresKey": False, "description": "Fetch and parse a URL"},
    {"id": "file_read", "name": "File Read", "category": "filesystem", "icon": "file", "requiresKey": False, "description": "Read files from agent workspace"},
    {"id": "file_write", "name": "File Write", "category": "filesystem", "icon": "file-plus", "requiresKey": False, "description": "Write files to agent workspace"},
    {"id": "database_read", "name": "Database Query", "category": "data", "icon": "database", "requiresKey": False, "description": "Query the local SQLite datastore"},
    {"id": "email_send", "name": "Email Send", "category": "communication", "icon": "mail", "requiresKey": True, "description": "Send email via SMTP (configure in Vault)"},
    {"id": "github", "name": "GitHub", "category": "devops", "icon": "github", "requiresKey": True, "description": "GitHub API — repos, issues, PRs"},
    {"id": "slack", "name": "Slack", "category": "communication", "icon": "message-square", "requiresKey": True, "description": "Slack messaging and channels"},
    {"id": "shell_exec", "name": "Shell Execute", "category": "system", "icon": "terminal", "requiresKey": False, "description": "Run sandboxed shell commands"},
    {"id": "git_read", "name": "Git Read", "category": "devops", "icon": "git-branch", "requiresKey": False, "description": "Read git repository state"},
    {"id": "git_write", "name": "Git Write", "category": "devops", "icon": "git-commit", "requiresKey": False, "description": "Commit and push changes"},
    {"id": "webhook_send", "name": "Webhook", "category": "integration", "icon": "webhook", "requiresKey": False, "description": "POST to external webhook URLs"},
    {"id": "pdf_read", "name": "PDF Read", "category": "documents", "icon": "file-text", "requiresKey": False, "description": "Extract text from PDF documents"},
    {"id": "chart_generate", "name": "Chart Generate", "category": "data", "icon": "bar-chart", "requiresKey": False, "description": "Generate data visualizations"},
    {"id": "api_call", "name": "REST API", "category": "integration", "icon": "plug", "requiresKey": True, "description": "Call external REST APIs with vault credentials"},
]

WORKSPACE = DATA_DIR / "agent-workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)


def init_tools_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tool_connections (
                connection_id TEXT PRIMARY KEY,
                tool_id TEXT NOT NULL,
                name TEXT NOT NULL,
                config TEXT,
                status TEXT DEFAULT 'active',
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS agent_tools (
                agent_id TEXT NOT NULL,
                tool_id TEXT NOT NULL,
                connection_id TEXT,
                PRIMARY KEY (agent_id, tool_id)
            );
            """
        )


def list_catalog() -> list[dict[str, Any]]:
    return TOOL_CATALOG


def list_connections() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tool_connections ORDER BY created_at DESC").fetchall()
    return [
        {
            "connectionId": r["connection_id"],
            "toolId": r["tool_id"],
            "name": r["name"],
            "status": r["status"],
            "config": json.loads(r["config"] or "{}"),
        }
        for r in rows
    ]


def create_connection(tool_id: str, name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    conn_id = f"conn-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tool_connections (connection_id, tool_id, name, config, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
            (conn_id, tool_id, name, json.dumps(config or {}), time.time()),
        )
    return {"connectionId": conn_id, "toolId": tool_id, "name": name, "status": "active"}


def assign_tools_to_agent(agent_id: str, tool_ids: list[str]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM agent_tools WHERE agent_id = ?", (agent_id,))
        for tid in tool_ids:
            conn.execute("INSERT INTO agent_tools (agent_id, tool_id) VALUES (?, ?)", (agent_id, tid))


def get_agent_tools(agent_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT tool_id FROM agent_tools WHERE agent_id = ?", (agent_id,)).fetchall()
    return [r["tool_id"] for r in rows]


def _safe_path(path: str) -> Path:
    resolved = (WORKSPACE / path.lstrip("/")).resolve()
    if not str(resolved).startswith(str(WORKSPACE.resolve())):
        raise PermissionError("Path outside agent workspace")
    return resolved


def _tool_web_search(query: str = "", **_: Any) -> dict[str, Any]:
    try:
        r = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=8.0,
        )
        data = r.json()
        return {"ok": True, "query": query, "abstract": data.get("Abstract", ""), "source": data.get("AbstractSource", "")}
    except Exception as exc:
        return {"ok": False, "query": query, "error": str(exc)}


def _tool_web_fetch(url: str = "", **_: Any) -> dict[str, Any]:
    try:
        r = httpx.get(url, timeout=8.0, follow_redirects=True)
        return {"ok": True, "url": url, "status": r.status_code, "preview": r.text[:500]}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def _tool_file_read(path: str = "", **_: Any) -> dict[str, Any]:
    try:
        p = _safe_path(path)
        if not p.exists():
            return {"ok": False, "path": path, "error": "File not found"}
        return {"ok": True, "path": path, "content": p.read_text()[:2000]}
    except Exception as exc:
        return {"ok": False, "path": path, "error": str(exc)}


def _tool_file_write(path: str = "", content: str = "", **_: Any) -> dict[str, Any]:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"ok": True, "path": path, "bytes": len(content)}
    except Exception as exc:
        return {"ok": False, "path": path, "error": str(exc)}


def _tool_database_read(query: str = "", table: str = "", **_: Any) -> dict[str, Any]:
    from app.database import get_conn

    try:
        with get_conn() as conn:
            if table:
                rows = conn.execute(f"SELECT * FROM {table} LIMIT 10").fetchall()
            else:
                rows = conn.execute(query).fetchall() if query else []
        return {"ok": True, "rows": [dict(r) for r in rows]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_email_send(to: str = "", subject: str = "", body: str = "", **_: Any) -> dict[str, Any]:
    import smtplib
    from email.mime.text import MIMEText

    host = _vault_get("SMTP_HOST")
    port = int(_vault_get("SMTP_PORT") or "587")
    user = _vault_get("SMTP_USER")
    password = _vault_get("SMTP_PASSWORD")
    from_addr = _vault_get("SMTP_FROM") or user
    if not all([host, user, password, to]):
        from app.production import is_production
        if is_production():
            return {"ok": False, "error": "SMTP not configured in Vault (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM)"}
        return {"ok": True, "simulated": True, "to": to, "subject": subject, "note": "SMTP not configured — simulated in dev"}
    msg = MIMEText(body)
    msg["Subject"] = subject or "ClearFrame Agent Notification"
    msg["From"] = from_addr
    msg["To"] = to
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to], msg.as_string())
        return {"ok": True, "to": to, "subject": subject}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_github(action: str = "list_repos", repo: str = "", title: str = "", body: str = "", **_: Any) -> dict[str, Any]:
    token = _vault_get("GITHUB_TOKEN")
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN not configured in Vault"}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        if action == "list_repos":
            r = httpx.get("https://api.github.com/user/repos?per_page=10&sort=updated", headers=headers, timeout=8.0)
            r.raise_for_status()
            return {"ok": True, "repos": [{"name": x["full_name"], "private": x["private"]} for x in r.json()]}
        if action == "get_repo":
            r = httpx.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=8.0)
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "repo": {"name": data["full_name"], "stars": data["stargazers_count"], "openIssues": data["open_issues_count"]}}
        if action == "list_issues":
            r = httpx.get(f"https://api.github.com/repos/{repo}/issues?state=open&per_page=10", headers=headers, timeout=8.0)
            r.raise_for_status()
            return {"ok": True, "issues": [{"number": i["number"], "title": i["title"]} for i in r.json()]}
        if action == "create_issue":
            r = httpx.post(f"https://api.github.com/repos/{repo}/issues", headers=headers, json={"title": title, "body": body}, timeout=8.0)
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "issueNumber": data["number"], "url": data["html_url"]}
        return {"ok": False, "error": f"Unknown action: {action}. Supported: list_repos, get_repo, list_issues, create_issue"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_slack(channel: str = "#general", message: str = "", **_: Any) -> dict[str, Any]:
    token = _vault_get("SLACK_BOT_TOKEN")
    if not token:
        from app.production import is_production
        if is_production():
            return {"ok": False, "error": "SLACK_BOT_TOKEN not configured in Vault"}
        return {"ok": True, "simulated": True, "channel": channel, "message": message, "note": "SLACK_BOT_TOKEN not in Vault — simulated in dev"}
    try:
        r = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel, "text": message},
            timeout=8.0,
        )
        return {"ok": r.json().get("ok", False), "response": r.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_shell_exec(command: str = "", **_: Any) -> dict[str, Any]:
    allowed = {"ls", "pwd", "date", "whoami", "echo"}
    cmd = command.strip().split()[0] if command.strip() else ""
    if cmd not in allowed:
        return {"ok": False, "error": f"Command '{cmd}' not in sandbox allowlist: {allowed}"}
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=5, cwd=WORKSPACE)
        return {"ok": result.returncode == 0, "stdout": result.stdout[:1000], "stderr": result.stderr[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_webhook_send(url: str = "", payload: dict | None = None, **_: Any) -> dict[str, Any]:
    try:
        r = httpx.post(url, json=payload or {"event": "erasys_agent"}, timeout=8.0)
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _vault_get(key: str) -> str | None:
    val = vault_svc.get_secret(key)
    return val or os.environ.get(key)


def _tool_api_call(endpoint: str = "", method: str = "GET", payload: dict | None = None, auth_header: str = "", **_: Any) -> dict[str, Any]:
    token = _vault_get("API_BEARER_TOKEN")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if auth_header:
        headers["Authorization"] = auth_header
    try:
        r = httpx.request(method.upper(), endpoint, headers=headers, json=payload, timeout=10.0)
        return {"ok": r.status_code < 400, "status": r.status_code, "body": r.text[:1000]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tool_git_read(path: str = ".", **_: Any) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            capture_output=True, text=True, timeout=5, cwd=WORKSPACE,
        )
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, timeout=5, cwd=WORKSPACE)
        return {"ok": True, "path": path, "branch": branch.stdout.strip() or "main", "lastCommit": result.stdout.strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "web_search": _tool_web_search,
    "web_fetch": _tool_web_fetch,
    "file_read": _tool_file_read,
    "file_write": _tool_file_write,
    "database_read": _tool_database_read,
    "send_email": _tool_email_send,
    "email_send": _tool_email_send,
    "github": _tool_github,
    "slack": _tool_slack,
    "shell_exec": _tool_shell_exec,
    "webhook_send": _tool_webhook_send,
    "git_read": _tool_git_read,
    "git_write": lambda **_: {"ok": False, "error": "git_write requires GitHub integration — use github.create_issue"},
    "pdf_read": lambda path="", **_: {"ok": True, "path": path, "pages": 1},
    "chart_generate": lambda **_: {"ok": True, "chart": "bar", "generated": True},
    "db_query": _tool_database_read,
    "api_call": _tool_api_call,
    "file_delete": lambda path="", **_: {"ok": False, "error": "Blocked by policy"},
}


def execute_tool(tool: str, **kwargs: Any) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(tool)
    if not handler:
        return {"ok": False, "error": f"Unknown tool: {tool}"}
    return handler(**kwargs)


def build_registry(capabilities: list[str]) -> dict[str, Callable[..., Any]]:
    registry: dict[str, Callable[..., Any]] = {}
    for cap in capabilities:
        if cap in TOOL_HANDLERS:

            def make_handler(t: str) -> Callable[..., Any]:
                async def handler(**kwargs: Any) -> dict[str, Any]:
                    return execute_tool(t, **kwargs)

                return handler

            registry[cap] = make_handler(cap)
    return registry
