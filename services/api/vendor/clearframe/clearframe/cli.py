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


# ── start ─────────────────────────────────────────────────────────────────────

@app.command()
def start(
    host: str = typer.Option("127.0.0.1", help="Bind address. Do NOT change to 0.0.0.0 in production."),
    port: int = typer.Option(7477, help="Port for the AgentOps API."),
) -> None:
    """Start the ClearFrame AgentOps server."""
    from clearframe.core.config import ClearFrameConfig, OpsConfig
    from clearframe.ops.server  import create_ops_app

    config          = ClearFrameConfig(ops=OpsConfig(host=host, port=port))
    ops_app, token  = create_ops_app(config.ops)

    # ── FIX 1: write token to disk — never echo to terminal ──────────────
    token_path = Path.home() / ".clearframe" / "ops-token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    token_path.chmod(0o600)
    # ─────────────────────────────────────────────────────────────────────

    console.print(f"\n[bold green]✓ ClearFrame AgentOps[/bold green] → http://{host}:{port}")
    console.print(f"  [yellow]Auth token saved →[/yellow] [cyan]{token_path}[/cyan]")
    console.print("  [dim]Load it:  export CF_OPS_TOKEN=$(cat ~/.clearframe/ops-token)[/dim]\n")
    console.print("  [dim]Press Ctrl+C to stop.[/dim]\n")

    uvicorn.run(ops_app, host=host, port=port, log_level="warning")


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
