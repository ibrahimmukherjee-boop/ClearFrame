#!/usr/bin/env bash
# Minimal-cost ClearFrame deploy for enterprise demo EC2 (~$18/mo t3.small).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

INSTANCE_ID="${INSTANCE_ID:-i-08d17d775371f32f1}"
TARGET_TYPE="${TARGET_TYPE:-t3.small}"
REGION="${AWS_REGION:-us-east-1}"
KEY_FILE="${KEY_FILE:-${ROOT}/clearframe-deploy-key.pem}"
ENV_FILE="${ROOT}/.env.production"

echo "==> ClearFrame minimal deploy (AI Governance and Safety)"

# 1. Build frontend locally (avoids Node on EC2)
echo "==> Building frontend locally..."
npm run build

# 2. Ensure production env exists
if [ ! -f "$ENV_FILE" ]; then
  echo "==> Generating .env.production"
  cat > "$ENV_FILE" <<EOF
CLEARFRAME_ENV=production
POSTGRES_PASSWORD=$(openssl rand -hex 16)
CLEARFRAME_JWT_SECRET=$(openssl rand -hex 32)
CLEARFRAME_VAULT_PASSPHRASE=$(openssl rand -hex 24)
CLEARFRAME_AUDIT_SECRET=$(openssl rand -hex 32)
CLEARFRAME_ADMIN_PASSWORD=$(openssl rand -hex 16)
CLEARFRAME_CORS=https://PLACEHOLDER
USE_OLLAMA=false
EOF
fi

# 3. Ensure instance is running (never stop/resize unless ALLOW_EC2_RESIZE=1)
CURRENT_TYPE=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].InstanceType' --output text)
STATE=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text)
if [ "$STATE" = "stopped" ] || [ "$STATE" = "stopping" ]; then
  echo "==> Starting stopped instance..."
  aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
  aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
elif [ "$CURRENT_TYPE" != "$TARGET_TYPE" ] && [ "${ALLOW_EC2_RESIZE:-0}" = "1" ]; then
  echo "==> Attempting resize ${CURRENT_TYPE} → ${TARGET_TYPE}..."
  if aws ec2 stop-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null 2>&1; then
    aws ec2 wait instance-stopped --region "$REGION" --instance-ids "$INSTANCE_ID" 2>/dev/null || true
    if aws ec2 modify-instance-attribute --region "$REGION" --instance-id "$INSTANCE_ID" --instance-type "{\"Value\": \"${TARGET_TYPE}\"}" 2>/dev/null; then
      aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
      aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
      echo "    Resized to ${TARGET_TYPE}"
    else
      echo "    Resize skipped (no IAM permission) — starting as ${CURRENT_TYPE}"
      aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
      aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
    fi
  fi
fi

PUBLIC_IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
PUBLIC_DNS=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
HOST_URL="http://${PUBLIC_IP}"

CORS="http://${PUBLIC_DNS},http://${PUBLIC_IP},https://${PUBLIC_DNS},https://${PUBLIC_IP}"
if grep -q "PLACEHOLDER" "$ENV_FILE" 2>/dev/null; then
  sed -i.bak "s|https://PLACEHOLDER|https://${PUBLIC_DNS}|g" "$ENV_FILE"
fi
grep -q "^CLEARFRAME_CORS=" "$ENV_FILE" && sed -i.bak "s|^CLEARFRAME_CORS=.*|CLEARFRAME_CORS=${CORS}|" "$ENV_FILE" || echo "CLEARFRAME_CORS=${CORS}" >> "$ENV_FILE"

echo "==> Target: ${PUBLIC_IP} (${PUBLIC_DNS})"
echo "==> Waiting for SSH..."
for i in $(seq 1 40); do
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$KEY_FILE" "ec2-user@${PUBLIC_IP}" "echo ok" 2>/dev/null && break
  sleep 5
done

# 4. Package (includes pre-built dist/)
TARBALL="/tmp/clearframe-minimal.tar.gz"
tar -czf "$TARBALL" \
  --exclude='node_modules' \
  --exclude='backend/.venv' \
  --exclude='backend/data' \
  --exclude='.git' \
  -C "$ROOT" .

scp -o StrictHostKeyChecking=no -i "$KEY_FILE" "$TARBALL" "$ENV_FILE" "ec2-user@${PUBLIC_IP}:/tmp/"

echo "==> Deploying on EC2..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ec2-user@${PUBLIC_IP}" bash <<REMOTE
set -e
# Swap for safe Docker builds on 2GB RAM
if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

sudo mkdir -p /opt/clearframe/app
sudo tar -xzf /tmp/clearframe-minimal.tar.gz -C /opt/clearframe/app 2>/dev/null || sudo tar -xzf /tmp/clearframe-minimal.tar.gz -C /opt/clearframe/app
sudo cp /tmp/.env.production /opt/clearframe/app/.env.production
sudo cp /tmp/.env.production /opt/clearframe/app/.env
sudo chown -R ec2-user:ec2-user /opt/clearframe/app
cd /opt/clearframe/app
chmod +x scripts/generate-tls-cert.sh
export CLEARFRAME_DOMAIN=${PUBLIC_DNS}
./scripts/generate-tls-cert.sh docker/certs

echo "==> Building image (Dockerfile.prod — no Node build)..."
sudo docker build -f Dockerfile.prod -t clearframe-stack:latest . 2>&1 | tail -5

echo "==> Starting stack..."
if sudo docker compose version >/dev/null 2>&1; then
  DC="sudo docker compose"
else
  DC="sudo docker-compose"
fi
\$DC -f docker-compose.minimal.yml --env-file .env.production up -d 2>&1

echo "==> Waiting for health..."
for i in \$(seq 1 30); do
  if curl -sf http://localhost/api/health 2>/dev/null | grep -q '"status":"ok"'; then
    echo "HEALTH OK"
    break
  fi
  sleep 5
done

sudo docker compose -f docker-compose.minimal.yml ps 2>/dev/null || sudo docker-compose -f docker-compose.minimal.yml ps

echo "==> Installing uptime watchdog (systemd timer + Docker on boot)..."
chmod +x scripts/ec2-watchdog.sh 2>/dev/null || true
sudo touch /var/log/clearframe-watchdog.log
sudo chown ec2-user:ec2-user /var/log/clearframe-watchdog.log
sudo systemctl enable docker 2>/dev/null || true
sudo cp scripts/clearframe-watchdog.service /etc/systemd/system/
sudo cp scripts/clearframe-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clearframe-watchdog.timer
sudo docker update --restart unless-stopped \$(sudo docker ps -q) 2>/dev/null || true
REMOTE

ADMIN_PW=$(grep CLEARFRAME_ADMIN_PASSWORD "$ENV_FILE" | cut -d= -f2)

echo ""
echo "=============================================="
echo " ClearFrame LIVE — AI Governance and Safety"
echo "=============================================="
echo " URL:      http://${PUBLIC_IP}"
echo " (HTTP recommended — avoids self-signed HTTPS warnings)"
echo " Login:    admin@erasys.local"
echo " Password: ${ADMIN_PW}"
echo " Instance: ${INSTANCE_ID} (${TARGET_TYPE})"
echo " SSH:      ssh -i ${KEY_FILE} ec2-user@${PUBLIC_IP}"
echo ""
echo " Use HTTP for reliable demo access (no certificate warning)."
echo " HTTPS is available but uses a self-signed certificate."
echo "=============================================="

# Remote smoke test
sleep 3
curl -sf "${HOST_URL}/api/health" | head -c 300 || echo "(health check from local — verify in browser)"
