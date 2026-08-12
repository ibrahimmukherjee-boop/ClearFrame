#!/usr/bin/env bash
# ClearFrame EC2 one-shot installer
# Usage:  curl -fsSL ... | bash   OR   bash deploy/install-ec2.sh
set -euo pipefail

PORT="${CLEARFRAME_PORT:-8080}"
APP_DIR="${CLEARFRAME_HOME:-$HOME/clearframe-deploy}"
REPO_URL="${CLEARFRAME_REPO:-https://github.com/ibrahimmukherjee-boop/ClearFrame.git}"
BRANCH="${CLEARFRAME_BRANCH:-cursor/nexus-sandbox-demo-be86}"

echo "==> ClearFrame EC2 install"
echo "    App dir: $APP_DIR"
echo "    Port:    $PORT"

sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl

mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" pull origin "$BRANCH" || true
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ./clearframe \
  -e ./nexus-sandbox/components/trust-registry \
  -e ./nexus-sandbox/components/aegis \
  -e ./nexus-sandbox/components/sonar

# Open firewall if ufw is active
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q active; then
  sudo ufw allow "${PORT}/tcp" || true
fi

# systemd unit
SERVICE_FILE="/etc/systemd/system/clearframe.service"
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=ClearFrame Nexus Protocol
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/.venv/bin:/usr/bin
Environment=CLEARFRAME_HOST=0.0.0.0
Environment=CLEARFRAME_PORT=$PORT
Environment=CLEARFRAME_DEMO=1
Environment=NEXUS_HOME=$HOME/.nexus
ExecStart=$APP_DIR/.venv/bin/clearframe serve --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable clearframe
sudo systemctl restart clearframe

sleep 2
PUBLIC_IP="$(curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/public-ipv4 || hostname -I | awk '{print $1}')"

echo ""
echo "════════════════════════════════════════════════════"
echo "  ClearFrame is running"
echo "  Open:  http://${PUBLIC_IP}:${PORT}/"
echo "  Login: NONE (demo mode)"
echo "  Logs:  sudo journalctl -u clearframe -f"
echo "════════════════════════════════════════════════════"
echo ""
echo "Security group: allow inbound TCP ${PORT}"
echo ""
