"""ClearFrame CLI — clearframe init / audit-verify / audit-tail / ops-start / version"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="clearframe",
    help="ClearFrame — AI agent protocol with auditability and safety controls.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(name: str = typer.Argument(..., help="Project name")) -> None:
    """Initialise a new ClearFrame agent project."""
    path = Path(name)
    path.mkdir(exist_ok=True)
    (path / "agent.py").write_text(
        f'"""ClearFrame agent: {name}"""\n\n'
        "import asyncio\n"
        "from clearframe import AgentSession, GoalManifest, ClearFrameConfig\n"
        "from clearframe.core.manifest import ToolPermission\n\n\n"
        "async def main() -> None:\n"
        "    config = ClearFrameConfig()\n"
        "    manifest = GoalManifest(\n"
        "        goal='Describe your agent goal here',\n"
        "        permitted_tools=[ToolPermission(tool_name='web_search')],\n"
        "    )\n"
        "    async with AgentSession(config, manifest) as session:\n"
        "        result = await session.call_tool('web_search', query='hello world')\n"
        "        print(result)\n\n\n"
        "if __name__ == '__main__':\n"
        "    asyncio.run(main())\n"
    )
    (path / "clearframe.json").write_text(
        json.dumps({"name": name, "version": "0.1.0"}, indent=2) + "\n"
    )
    console.print(f"[green]✓[/green] Initialised ClearFrame project: [bold]{name}[/bold]")
    console.print(f"  Edit [cyan]{name}/agent.py[/cyan] to define your agent.")
    console.print(f"  Run: [cyan]cd {name} && python agent.py[/cyan]")


@app.command(name="audit-verify")
def audit_verify(
    session_id: str = typer.Option(None, "--session", "-s", help="Filter by session ID"),
    log_path: Path = typer.Option(
        Path.home() / ".clearframe" / "audit.log", "--log", help="Path to audit log"
    ),
) -> None:
    """Verify HMAC chain integrity of the audit log."""
    from clearframe.core.audit import AuditLog
    from clearframe.core.config import AuditConfig

    cfg = AuditConfig(log_path=log_path)
    audit = AuditLog(cfg)
    ok, errors = audit.verify()
    if ok:
        console.print("[green]✓ Audit log integrity verified — no tampering detected.[/green]")
    else:
        console.print(f"[red]✗ TAMPERING DETECTED — {len(errors)} error(s):[/red]")
        for err in errors:
            console.print(f"  [red]{err}[/red]")
        raise typer.Exit(code=1)


@app.command(name="audit-tail")
def audit_tail(
    n: int = typer.Option(20, "--lines", "-n", help="Number of entries to show"),
    log_path: Path = typer.Option(
        Path.home() / ".clearframe" / "audit.log", "--log", help="Path to audit log"
    ),
) -> None:
    """Show recent audit log entries."""
    from clearframe.core.audit import AuditLog
    from clearframe.core.config import AuditConfig

    cfg = AuditConfig(log_path=log_path)
    audit = AuditLog(cfg)
    entries = audit.tail(n)
    if not entries:
        console.print("[dim]No audit entries found.[/dim]")
        return
    table = Table(title=f"Last {n} Audit Entries", show_lines=True)
    table.add_column("Seq", style="dim", width=6)
    table.add_column("Event", style="cyan")
    table.add_column("Session", style="dim", width=14)
    table.add_column("Timestamp", style="dim")
    for e in entries:
        table.add_row(
            str(e.get("seq", "")),
            e.get("event_type", ""),
            str(e.get("session_id", ""))[:12] + "…",
            str(e.get("timestamp", ""))[:19],
        )
    console.print(table)


@app.command(name="ops-start")
def ops_start(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(7477, "--port"),
) -> None:
    """Start the AgentOps control plane server."""
    import uvicorn
    from clearframe.core.config import OpsConfig
    from clearframe.ops.server import create_ops_app, _ops_token

    config = OpsConfig(host=host, port=port)
    ops_app = create_ops_app(config)
    console.print(f"[green]✓ ClearFrame AgentOps starting at http://{host}:{port}[/green]")
    console.print(f"  [yellow]Auth token:[/yellow] {_ops_token}")
    console.print("  [dim]Keep this token private — it grants full control.[/dim]")
    uvicorn.run(ops_app, host=host, port=port)


@app.command()
def version() -> None:
    """Show ClearFrame version."""
    from clearframe import __version__
    console.print(f"ClearFrame v{__version__}")


if __name__ == "__main__":
    app()
