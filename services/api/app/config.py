"""Erasys ClearFrame Stack — local enterprise API."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CLEARFRAME_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "erasys.db"
AUDIT_PATH = DATA_DIR / "audit.log"
AUDIT_SECRET_PATH = DATA_DIR / "audit.secret"
VAULT_PATH = DATA_DIR / "vault.enc"
VAULT_SALT_PATH = DATA_DIR / "vault.salt"

API_HOST = os.environ.get("CLEARFRAME_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("PORT") or os.environ.get("CLEARFRAME_API_PORT", "8080"))
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CLEARFRAME_CORS",
    "http://localhost:5173,http://127.0.0.1:5173,https://ibrahimmukherjee-boop.github.io",
).split(",") if o.strip()]

DEFAULT_VAULT_PASSPHRASE = os.environ.get("CLEARFRAME_VAULT_PASSPHRASE", "erasys-local-dev")

CLEARFRAME_RUNTIME_DIR = DATA_DIR / "clearframe-runtime"
CF_OPS_HOST = os.environ.get("CLEARFRAME_OPS_HOST", "127.0.0.1")
CF_OPS_PORT = int(os.environ.get("CLEARFRAME_OPS_PORT", "7477"))
CF_OPS_TOKEN_PATH = Path(os.environ.get("CF_OPS_TOKEN_PATH", DATA_DIR / "ops-token"))
USE_CLEARFRAME_OPS = os.environ.get("USE_CLEARFRAME_OPS", "true").lower() in {"1", "true", "yes"}
USE_CLEARFRAME_RUNTIME = os.environ.get("USE_CLEARFRAME_RUNTIME", "true").lower() in {"1", "true", "yes"}

# Enterprise auth
JWT_SECRET = os.environ.get("CLEARFRAME_JWT_SECRET", "erasys-enterprise-jwt-change-in-production")
JWT_EXPIRY_HOURS = int(os.environ.get("CLEARFRAME_JWT_EXPIRY_HOURS", "8"))
AUTH_REQUIRED = os.environ.get("CLEARFRAME_AUTH", "true").lower() in {"1", "true", "yes"}
# Off by default: self-signed demo TLS + HSTS permanently breaks browser access.
HSTS_ENABLED = os.environ.get("CLEARFRAME_HSTS", "false").lower() in {"1", "true", "yes"}

# Ollama LLM
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
USE_OLLAMA = os.environ.get("USE_OLLAMA", "true").lower() in {"1", "true", "yes"}

# Optional enterprise data stores
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
REDIS_URL = os.environ.get("REDIS_URL", "")
