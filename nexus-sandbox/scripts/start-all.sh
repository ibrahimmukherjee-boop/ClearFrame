#!/usr/bin/env bash
# Nexus Protocol — start all sandbox services
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
export PYTHONPATH="${ROOT}/components/trust-registry:${ROOT}/components/aegis:${ROOT}/components/sonar:${ROOT}/../clearframe/clearframe:${PYTHONPATH:-}"

echo "Installing Nexus sandbox components..."
pip install -q -e "${ROOT}/components/trust-registry" -e "${ROOT}/components/aegis" -e "${ROOT}/components/sonar"
pip install -q pydantic cryptography fastapi "uvicorn[standard]" typer rich httpx anyio slowapi 2>/dev/null || true

mkdir -p "${HOME}/.nexus"

echo "Starting TrustRegistry on :8001..."
$PY -m trust_registry.cli --host 0.0.0.0 --port 8001 &
PID_TR=$!

echo "Starting Sonar on :8002..."
$PY -m sonar.cli --host 0.0.0.0 --port 8002 &
PID_SN=$!

echo "Starting Aegis on :8003..."
$PY -m aegis.cli --host 0.0.0.0 --port 8003 &
PID_AG=$!

echo "Starting ClearFrame AgentOps on :7477..."
export PATH="$HOME/.local/bin:$PATH"
if command -v clearframe >/dev/null 2>&1; then
  clearframe ops-start --host 0.0.0.0 --port 7477 &
elif [ -d "${ROOT}/../clearframe/clearframe" ]; then
  (cd "${ROOT}/../clearframe/clearframe" && PYTHONPATH=. $PY -c "
from clearframe.core.config import ClearFrameConfig, OpsConfig
from clearframe.ops.server import create_ops_app
import uvicorn
app, _ = create_ops_app(ClearFrameConfig(ops=OpsConfig(host='0.0.0.0', port=7477)).ops)
uvicorn.run(app, host='0.0.0.0', port=7477, log_level='warning')
") &
else
  echo "WARN: clearframe not found"
fi
PID_CF=$!

sleep 3

echo "Starting Nexus dashboard on :8080..."
$PY "${ROOT}/demo/orchestrator.py" --no-start-deps &
PID_DASH=$!

sleep 2
$PY "${ROOT}/scripts/healthcheck.py" || true

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Nexus Protocol Sandbox is running"
echo "  Dashboard:     http://localhost:8080"
echo "  TrustRegistry:   http://localhost:8001/health"
echo "  Sonar:           http://localhost:8002/health"
echo "  Aegis:           http://localhost:8003/health"
echo "  ClearFrame:      http://localhost:7477/health"
echo "═══════════════════════════════════════════════════════"
echo "Press Ctrl+C to stop all services."

cleanup() {
  kill $PID_TR $PID_SN $PID_AG $PID_CF $PID_DASH 2>/dev/null || true
}
trap cleanup EXIT
wait
