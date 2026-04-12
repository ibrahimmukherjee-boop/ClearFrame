"""
ClearFrame Configuration

Secure defaults throughout. Every dangerous option is OFF by default.
Contrast with OpenClaw which binds to 0.0.0.0 and requires no auth.
"""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field


class VaultConfig(BaseModel):
    vault_path: Path = Field(default=Path("~/.clearframe/vault.enc").expanduser())
    salt_path: Path = Field(default=Path("~/.clearframe/vault.salt").expanduser())
    pbkdf2_iterations: int = 600_000   # OWASP 2024 minimum is 210,000 — we exceed it


class AuditConfig(BaseModel):
    log_path: Path = Field(default=Path("~/.clearframe/audit.log").expanduser())
    enabled: bool = True
    hmac_secret_env: str = "CLEARFRAME_AUDIT_SECRET"


class RTLConfig(BaseModel):
    rtl_path: Path = Field(default=Path("~/.clearframe/rtl").expanduser())
    enabled: bool = True


class GoalMonitorConfig(BaseModel):
    alignment_threshold: float = 0.55       # Below this → block or queue
    auto_approve_threshold: float = 0.85    # Above this → auto-approve
    pause_on_ambiguous: bool = True         # True → queue; False → block
    max_consecutive_low_scores: int = 3     # Suspend session after N low scores


class OpsConfig(BaseModel):
    host: str = "127.0.0.1"    # Localhost only — never 0.0.0.0 by default
    port: int = 7477
    require_auth: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class ClearFrameConfig(BaseModel):
    vault: VaultConfig = Field(default_factory=VaultConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    rtl: RTLConfig = Field(default_factory=RTLConfig)
    goal_monitor: GoalMonitorConfig = Field(default_factory=GoalMonitorConfig)
    ops: OpsConfig = Field(default_factory=OpsConfig)
    # Never bind to all interfaces by default (OpenClaw CVE-2024-6940 root cause)
    allow_remote_connections: bool = False
