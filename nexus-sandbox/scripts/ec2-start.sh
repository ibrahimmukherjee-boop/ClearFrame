#!/usr/bin/env bash
# Nexus Protocol — EC2 deployment (single port, no login)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
PORT="${NEXUS_PORT:-8080}"
HOST="${NEXUS_HOST:-0.0.0.0}"

echo "==> Installing Nexus Protocol sandbox..."
"$PY" -m pip install -q -r "${ROOT}/requirements.txt"
"$PY" -m pip install -q -e "${ROOT}/components/trust-registry" \
                 -e "${ROOT}/components/aegis" \
                 -e "${ROOT}/components/sonar"
"$PY" -m pip install -q pydantic cryptography fastapi "uvicorn[standard]" httpx typer rich anyio slowapi 2>/dev/null || true

# Optional ClearFrame from PyPI (auth disabled inside unified gateway)
"$PY" -m pip install -q clearframe 2>/dev/null || true

mkdir -p "${HOME}/.nexus"

# Detect EC2 public IP for display
PUBLIC_IP=""
if curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/public-ipv4 >/dev/null 2>&1; then
  PUBLIC_IP="$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4)"
  export NEXUS_PUBLIC_HOST="${NEXUS_PUBLIC_HOST:-$PUBLIC_IP}"
fi

export NEXUS_PORT="$PORT"
export NEXUS_HOST="$HOST"

echo ""
echo "==> Starting unified gateway on ${HOST}:${PORT}"
echo "    (All services on ONE port — no separate ports, no login)"
echo ""

if [ "$PORT" = "80" ] && [ "$(id -u)" != "0" ]; then
  echo "WARNING: Port 80 requires root. Using sudo..."
  exec sudo -E env "PATH=$PATH" "NEXUS_PORT=$PORT" "NEXUS_HOST=$HOST" "NEXUS_PUBLIC_HOST=${NEXUS_PUBLIC_HOST:-}" \
    "$PY" "${ROOT}/demo/unified_app.py"
else
  exec "$PY" "${ROOT}/demo/unified_app.py"
fi
