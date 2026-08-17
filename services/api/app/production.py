"""Production environment validation — blocks unsafe deploys."""
from __future__ import annotations

import os
import sys
from typing import Any

INSECURE_DEFAULTS = {
    "CLEARFRAME_JWT_SECRET": {
        "erasys-enterprise-jwt-change-in-production",
        "change-me-in-production",
        "change-me-in-production-use-openssl-rand",
    },
    "CLEARFRAME_VAULT_PASSPHRASE": {
        "erasys-local-dev",
        "change-me-in-production",
    },
    "CLEARFRAME_AUDIT_SECRET": {
        "erasys-local-audit-secret",
        "change-me-in-production",
    },
}


def is_production() -> bool:
    return os.environ.get("CLEARFRAME_ENV", "development").lower() in {"production", "prod"}


def validate_production_config() -> list[str]:
    """Return list of blocking errors. Empty = safe to start."""
    if not is_production():
        return []

    errors: list[str] = []
    for var, bad_values in INSECURE_DEFAULTS.items():
        val = os.environ.get(var, "")
        if not val or val in bad_values:
            errors.append(f"{var} must be set to a unique secret in production (not a default)")

    if os.environ.get("CLEARFRAME_AUTH", "true").lower() not in {"1", "true", "yes"}:
        errors.append("CLEARFRAME_AUTH must be true in production")

    if os.environ.get("CLEARFRAME_ALLOW_DEFAULT_PASSWORDS", "false").lower() in {"1", "true", "yes"}:
        errors.append("CLEARFRAME_ALLOW_DEFAULT_PASSWORDS must be false in production")

    cors = os.environ.get("CLEARFRAME_CORS", "")
    if "*" in cors:
        errors.append("CLEARFRAME_CORS must not contain wildcard in production")

    db_url = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
    if not db_url.startswith("postgresql"):
        errors.append("DATABASE_URL must be a PostgreSQL connection string in production")

    return errors


def enforce_or_exit() -> None:
    errors = validate_production_config()
    if errors:
        for e in errors:
            print(f"PRODUCTION CONFIG ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def production_status() -> dict[str, Any]:
    return {
        "environment": os.environ.get("CLEARFRAME_ENV", "development"),
        "production": is_production(),
        "configValid": len(validate_production_config()) == 0,
        "errors": validate_production_config(),
        "authRequired": os.environ.get("CLEARFRAME_AUTH", "true"),
    }
