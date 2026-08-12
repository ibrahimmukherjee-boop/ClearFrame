#!/usr/bin/env bash
# Re-deploy to an existing ClearFrame EC2 instance (minimal stack).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IP="${1:-}"
KEY_FILE="${KEY_FILE:-${ROOT}/clearframe-deploy-key.pem}"
ENV_FILE="${ROOT}/.env.production"
INSTANCE_ID="${INSTANCE_ID:-i-08d17d775371f32f1}"
REGION="${AWS_REGION:-us-east-1}"

if [ -z "$IP" ]; then
  IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
fi
echo "==> Redeploying ClearFrame to ${IP}"

echo "==> Building frontend locally..."
npm run build

PUBLIC_DNS=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text 2>/dev/null || echo "")
CORS="http://${PUBLIC_DNS},http://${IP},https://${PUBLIC_DNS},https://${IP}"
if [ -f "$ENV_FILE" ]; then
  grep -q "^CLEARFRAME_CORS=" "$ENV_FILE" && sed -i.bak "s|^CLEARFRAME_CORS=.*|CLEARFRAME_CORS=${CORS}|" "$ENV_FILE" \
    || echo "CLEARFRAME_CORS=${CORS}" >> "$ENV_FILE"
  grep -q "^CLEARFRAME_HSTS=" "$ENV_FILE" || echo "CLEARFRAME_HSTS=false" >> "$ENV_FILE"
fi

TARBALL="/tmp/clearframe-deploy.tar.gz"
tar -czf "$TARBALL" \
  --exclude='node_modules' \
  --exclude='backend/.venv' \
  --exclude='backend/data' \
  --exclude='.git' \
  -C "$ROOT" .

scp -o StrictHostKeyChecking=no -i "$KEY_FILE" "$TARBALL" "$ENV_FILE" "ec2-user@${IP}:/tmp/"

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ec2-user@${IP}" bash <<REMOTE
set -e
sudo mkdir -p /opt/clearframe/app
sudo tar -xzf /tmp/clearframe-deploy.tar.gz -C /opt/clearframe/app
sudo cp /tmp/.env.production /opt/clearframe/app/.env.production
sudo cp /tmp/.env.production /opt/clearframe/app/.env
sudo chown -R ec2-user:ec2-user /opt/clearframe/app
cd /opt/clearframe/app
chmod +x scripts/generate-tls-cert.sh scripts/ec2-watchdog.sh 2>/dev/null || true
export CLEARFRAME_DOMAIN=\$(curl -s http://169.254.169.254/latest/meta-data/public-hostname || hostname)
./scripts/generate-tls-cert.sh docker/certs 2>/dev/null || true

if sudo docker compose version >/dev/null 2>&1; then
  DC="sudo docker compose"
else
  DC="sudo docker-compose"
fi

echo "==> Building image..."
sudo docker build -f Dockerfile.prod -t clearframe-stack:latest . 2>&1 | tail -20
\$DC -f docker-compose.minimal.yml --env-file .env.production up -d --force-recreate

echo "==> Waiting for health..."
for i in \$(seq 1 36); do
  if curl -sf http://localhost/api/health 2>/dev/null | grep -q '"status":"ok"'; then
    echo "HEALTH OK"
    break
  fi
  sleep 5
done

\$DC -f docker-compose.minimal.yml ps

# Ensure watchdog is installed
if [ -f scripts/clearframe-watchdog.service ]; then
  sudo touch /var/log/clearframe-watchdog.log
  sudo chown ec2-user:ec2-user /var/log/clearframe-watchdog.log
  sudo cp scripts/clearframe-watchdog.service /etc/systemd/system/
  sudo cp scripts/clearframe-watchdog.timer /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now clearframe-watchdog.timer
fi
REMOTE

echo ""
echo "Redeploy complete: http://${IP}"
echo "Health: http://${IP}/api/health"
curl -sf "http://${IP}/api/health" | head -c 400 || echo "(verify in browser)"
echo
