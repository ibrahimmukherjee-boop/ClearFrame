"""
ClearFrame CLI
==============
Main entry point for the `clearframe` command.

Fix 1: Ops token is written to ~/.clearframe/ops-token (chmod 600).
       It is never printed to the terminal.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table   import Table

app     = typer.Typer(name="clearframe", help="ClearFrame — secure agentic AI runtime", no_args_is_help=True)
console = Console()


# ── serve (full stack — preferred for EC2 / production demo) ──────────────────

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address. Use 0.0.0.0 for EC2."),
    port: int = typer.Option(8080, help="Public port (open this in your security group)."),
    demo: bool = typer.Option(True, help="Demo mode — no login required."),
) -> None:
    """Start the full ClearFrame + Nexus Protocol stack (single port, branded UI)."""
    import os

    os.environ["CLEARFRAME_HOST"] = host
    os.environ["CLEARFRAME_PORT"] = str(port)
    os.environ["CLEARFRAME_DEMO"] = "1" if demo else "0"
    from clearframe.gateway_app import serve as run_gateway

    console.print("\n[bold]ClearFrame[/bold] · Nexus Protocol")
    console.print(f"  Binding [cyan]{host}:{port}[/cyan]  auth={'off' if demo else 'on'}\n")
    run_gateway(host=host, port=port)


# ── start / ops-start (AgentOps API only) ─────────────────────────────────────

@app.command()
def start(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(7477, help="Port for the AgentOps API."),
) -> None:
    """Start the ClearFrame AgentOps API only (no UI). Prefer `clearframe serve` for demos."""
    from clearframe.core.config import ClearFrameConfig, OpsConfig
    from clearframe.ops.server import create_ops_app

    config = ClearFrameConfig(ops=OpsConfig(host=host, port=port))
    ops_app, token = create_ops_app(config.ops)

    token_path = Path.home() / ".clearframe" / "ops-token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    token_path.chmod(0o600)

    console.print(f"\n[bold green]✓ ClearFrame AgentOps[/bold green] → http://{host}:{port}")
    console.print(f"  [yellow]Auth token saved →[/yellow] [cyan]{token_path}[/cyan]")
    console.print("  [dim]For full UI + stack: clearframe serve[/dim]\n")

    uvicorn.run(ops_app, host=host, port=port, log_level="warning")


@app.command("ops-start")
def ops_start(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(7477),
) -> None:
    """Alias for `start` (AgentOps API only)."""
    start(host=host, port=port)


# ── audit-verify ──────────────────────────────────────────────────────────────

@app.command("audit-verify")
def audit_verify(
    log_path: Path = typer.Option(
        Path("~/.clearframe/audit.log").expanduser(),
        help="Path to the audit log file.",
    ),
) -> None:
    """Verify the HMAC chain integrity of an audit log."""
    from clearframe.core.audit  import AuditLog
    from clearframe.core.config import AuditConfig

    config     = AuditConfig(log_path=log_path)
    audit      = AuditLog(config)
    ok, errors = audit.verify_chain()

    if ok:
        console.print("[bold green]✓ Audit log chain is intact.[/bold green]")
    else:
        console.print(f"[bold red]✗ {len(errors)} chain error(s) found:[/bold red]")
        for e in errors:
            console.print(f"  [red]•[/red] {e}")
        raise typer.Exit(code=1)


# ── rtl-replay ────────────────────────────────────────────────────────────────

@app.command("rtl-replay")
def rtl_replay(
    session_id: str = typer.Argument(..., help="Session ID to replay."),
    rtl_dir: Path   = typer.Option(
        Path("~/.clearframe/rtl").expanduser(),
        help="Directory containing RTL trace files.",
    ),
) -> None:
    """Replay and verify the reasoning trace for a session."""
    import hashlib
    from clearframe.core.config import RTLConfig
    from clearframe.monitor.rtl import RTL

    config = RTLConfig(rtl_path=rtl_dir)
    rtl    = RTL(session_id, config)
    steps  = rtl.replay()
    ok, errors = rtl.verify_hashes()

    if not steps:
        console.print(f"[yellow]No trace found for session {session_id}.[/yellow]")
        return

    table = Table("Seq", "Type", "Hash OK", "Content Preview", show_header=True)
    for step in steps:
        expected = hashlib.sha256(step.content.encode()).hexdigest()
        ok_flag  = "[green]✓[/green]" if step.content_hash == expected else "[red]✗[/red]"
        table.add_row(str(step.seq), step.step_type, ok_flag, step.content[:72])
    console.print(table)

    if not ok:
        console.print(f"\n[bold red]✗ {len(errors)} hash mismatch(es):[/bold red]")
        for e in errors:
            console.print(f"  [red]•[/red] {e}")
        raise typer.Exit(code=1)
    else:
        console.print(f"\n[green]✓ All {len(steps)} reasoning steps verified.[/green]")


# ── agent ─────────────────────────────────────────────────────────────────────

agent_app = typer.Typer(help="Create and validate governed agents from specs.")
app.add_typer(agent_app, name="agent")


@agent_app.command("new")
def agent_new(
    name: str = typer.Argument(..., help="Agent name."),
    out: Path = typer.Option(None, help="Output path (default: ./<name>.agent.yaml)."),
) -> None:
    """Scaffold a new agent spec (YAML) anyone can edit and run."""
    from clearframe.agents import TEMPLATE

    spec = TEMPLATE.model_copy(update={"name": name})
    path = out or Path(f"{name}.agent.yaml")
    spec.save(path)
    console.print(f"[green]✓[/green] Agent spec written → [cyan]{path}[/cyan]")
    console.print("  Edit the spec, then: [dim]clearframe agent validate " + str(path) + "[/dim]")


@agent_app.command("validate")
def agent_validate(path: Path = typer.Argument(..., help="Path to .agent.yaml")) -> None:
    """Validate an agent spec and its policy packs."""
    from clearframe.agents import load_spec
    from clearframe.policy import PolicyEngine

    spec = load_spec(path)
    engine = PolicyEngine.with_packs(*spec.policy_packs)
    console.print(f"[green]✓[/green] Spec [bold]{spec.name}[/bold] is valid.")
    console.print(f"  Goal:      {spec.goal}")
    console.print(f"  Tools:     {[t.name for t in spec.tools]}")
    console.print(f"  Policies:  {engine.pack_names}")
    console.print(f"  Trust:     {spec.trust_level}")


@agent_app.command("packs")
def agent_packs() -> None:
    """List available policy packs."""
    from clearframe.policy import packaged_packs, load_pack

    for name, path in packaged_packs().items():
        pack = load_pack(path)
        console.print(f"  [cyan]{name:14}[/cyan] {pack.get('title', '')}")


# ── bench ─────────────────────────────────────────────────────────────────────

@app.command()
def bench() -> None:
    """Run the NexusProtocol governance benchmark and print the scorecard."""
    from clearframe.bench import main as run_bench

    report = run_bench()
    np = report["nexusprotocol"]
    console.print(f"\n[bold]NexusProtocol Governance Benchmark[/bold] — {report['ran_at']}")
    console.print(f"  [green]NexusProtocol  {np['passed']}/{np['total']}[/green] controls enforced (measured live)\n")
    table = Table("Control", "Result", "Detail", show_header=True)
    for name, s in report["scenarios"].items():
        mark = "[green]PASS[/green]" if s["passed"] else "[red]FAIL[/red]"
        table.add_row(name, mark, s["detail"][:70])
    console.print(table)
    console.print("\n  Out-of-the-box comparison (vendor docs, Aug 2026):")
    for vendor, score in report["competitors_out_of_the_box"].items():
        console.print(f"    {vendor:22} {score['passed']}/{score['total']}")
    console.print(f"\n  Report → ~/.nexus/bench-report.json\n")


# ── vault ─────────────────────────────────────────────────────────────────────

vault_app = typer.Typer(help="Manage the ClearFrame credential vault.")
app.add_typer(vault_app, name="vault")


@vault_app.command("set")
def vault_set(
    name:       str  = typer.Argument(..., help="Credential name."),
    passphrase: str  = typer.Option(..., prompt=True, hide_input=True, help="Vault passphrase."),
) -> None:
    """Store a credential in the encrypted vault."""
    import getpass
    from clearframe.core.config import ClearFrameConfig
    from clearframe.core.vault  import Vault

    value = getpass.getpass(f"Value for '{name}': ")
    vault = Vault(ClearFrameConfig().vault)
    vault.unlock(passphrase)
    vault.set(name, value)
    vault.lock()
    console.print(f"[green]✓ Credential '{name}' saved.[/green]")


@vault_app.command("list")
def vault_list(
    passphrase: str = typer.Option(..., prompt=True, hide_input=True),
) -> None:
    """List credential names stored in the vault."""
    from clearframe.core.config import ClearFrameConfig
    from clearframe.core.vault  import Vault

    vault = Vault(ClearFrameConfig().vault)
    vault.unlock(passphrase)
    keys  = vault.list_keys()
    vault.lock()

    if not keys:
        console.print("[yellow]Vault is empty.[/yellow]")
    else:
        for k in keys:
            console.print(f"  [cyan]•[/cyan] {k}")


# ── version ───────────────────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """Print the ClearFrame version."""
    from clearframe import __version__
    console.print(f"ClearFrame v{__version__}")


if __name__ == "__main__":
    app()
