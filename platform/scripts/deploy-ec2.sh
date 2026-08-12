#!/usr/bin/env bash
# Provision a new AWS EC2 instance and deploy ClearFrame Stack with HTTPS + Postgres.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

INSTANCE_TYPE="${INSTANCE_TYPE:-t3.large}"
REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}"
KEY_NAME="${KEY_NAME:-clearframe-deploy-key}"
SG_NAME="${SG_NAME:-clearframe-stack-sg}"
INSTANCE_NAME="${INSTANCE_NAME:-clearframe-stack}"
AMI_ID="${AMI_ID:-}"

echo "==> ClearFrame EC2 Deploy (region: ${REGION})"

# Resolve Amazon Linux 2023 AMI
if [ -z "$AMI_ID" ]; then
  AMI_ID=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners amazon \
    --filters "Name=name,Values=al2023-ami-2023*-kernel-6.1-x86_64" "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text)
fi
echo "    AMI: ${AMI_ID}"

# Key pair
if ! aws ec2 describe-key-pairs --region "$REGION" --key-names "$KEY_NAME" &>/dev/null; then
  echo "==> Creating key pair ${KEY_NAME}"
  aws ec2 create-key-pair --region "$REGION" --key-name "$KEY_NAME" \
    --query 'KeyMaterial' --output text > "${ROOT}/${KEY_NAME}.pem"
  chmod 400 "${ROOT}/${KEY_NAME}.pem"
  echo "    Saved private key: ${ROOT}/${KEY_NAME}.pem"
else
  echo "    Using existing key pair: ${KEY_NAME}"
fi
KEY_FILE="${ROOT}/${KEY_NAME}.pem"

# Security group
VPC_ID=$(aws ec2 describe-vpcs --region "$REGION" --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" \
  --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  echo "==> Creating security group ${SG_NAME}"
  SG_ID=$(aws ec2 create-security-group --region "$REGION" \
    --group-name "$SG_NAME" --description "ClearFrame Stack HTTPS" --vpc-id "$VPC_ID" \
    --query 'GroupId' --output text)
  MY_IP=$(curl -s https://checkip.amazonaws.com || echo "0.0.0.0/0")
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 22 --cidr "${MY_IP}/32" 2>/dev/null || \
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 22 --cidr "0.0.0.0/0"
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 80 --cidr "0.0.0.0/0"
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 443 --cidr "0.0.0.0/0"
fi
echo "    Security group: ${SG_ID}"

# Generate production secrets if .env.production missing
ENV_FILE="${ROOT}/.env.production"
if [ ! -f "$ENV_FILE" ]; then
  echo "==> Generating .env.production"
  JWT_SECRET=$(openssl rand -hex 32)
  VAULT_PW=$(openssl rand -hex 24)
  AUDIT_SECRET=$(openssl rand -hex 32)
  ADMIN_PW=$(openssl rand -hex 16)
  PG_PW=$(openssl rand -hex 16)
  cat > "$ENV_FILE" <<EOF
CLEARFRAME_ENV=production
POSTGRES_PASSWORD=${PG_PW}
CLEARFRAME_JWT_SECRET=${JWT_SECRET}
CLEARFRAME_VAULT_PASSPHRASE=${VAULT_PW}
CLEARFRAME_AUDIT_SECRET=${AUDIT_SECRET}
CLEARFRAME_ADMIN_PASSWORD=${ADMIN_PW}
CLEARFRAME_CORS=https://PLACEHOLDER
USE_OLLAMA=false
EOF
  echo "    Admin password saved in .env.production (CLEARFRAME_ADMIN_PASSWORD)"
fi

# User data — install Docker on Amazon Linux 2023
USER_DATA=$(cat <<'USERDATA'
#!/bin/bash
set -e
dnf update -y
dnf install -y docker git
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user
mkdir -p /opt/clearframe
chown ec2-user:ec2-user /opt/clearframe
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
echo "Docker ready" > /opt/clearframe/bootstrap.done
USERDATA
)

echo "==> Launching EC2 instance (${INSTANCE_TYPE})"
INSTANCE_ID=$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":40,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${INSTANCE_NAME}}]" \
  --user-data "$USER_DATA" \
  --query 'Instances[0].InstanceId' --output text)
echo "    Instance ID: ${INSTANCE_ID}"

echo "==> Waiting for instance to run..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
PUBLIC_IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
PUBLIC_DNS=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
echo "    Public IP: ${PUBLIC_IP}"
echo "    Public DNS: ${PUBLIC_DNS}"

# Update CORS in env file
HOST_URL="https://${PUBLIC_DNS}"
if grep -q "PLACEHOLDER" "$ENV_FILE" 2>/dev/null; then
  sed -i.bak "s|https://PLACEHOLDER|${HOST_URL}|g" "$ENV_FILE"
fi
sed -i.bak "s|^CLEARFRAME_CORS=.*|CLEARFRAME_CORS=${HOST_URL}|" "$ENV_FILE" 2>/dev/null || true

echo "==> Waiting for SSH (up to 3 min)..."
for i in $(seq 1 36); do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$KEY_FILE" "ec2-user@${PUBLIC_IP}" "test -f /opt/clearframe/bootstrap.done" 2>/dev/null; then
    break
  fi
  sleep 5
done

echo "==> Packaging and uploading ClearFrame..."
TARBALL="/tmp/clearframe-deploy.tar.gz"
tar -czf "$TARBALL" \
  --exclude='node_modules' \
  --exclude='backend/.venv' \
  --exclude='backend/data' \
  --exclude='.git' \
  --exclude='dist' \
  -C "$ROOT" .

scp -o StrictHostKeyChecking=no -i "$KEY_FILE" "$TARBALL" "ec2-user@${PUBLIC_IP}:/tmp/clearframe-deploy.tar.gz"
scp -o StrictHostKeyChecking=no -i "$KEY_FILE" "$ENV_FILE" "ec2-user@${PUBLIC_IP}:/tmp/.env.production"

echo "==> Building and starting on EC2..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ec2-user@${PUBLIC_IP}" bash <<REMOTE
set -e
sudo rm -rf /opt/clearframe/app
sudo mkdir -p /opt/clearframe/app
sudo tar -xzf /tmp/clearframe-deploy.tar.gz -C /opt/clearframe/app
sudo cp /tmp/.env.production /opt/clearframe/app/.env.production
sudo cp /tmp/.env.production /opt/clearframe/app/.env
sudo chown -R ec2-user:ec2-user /opt/clearframe/app
cd /opt/clearframe/app
chmod +x scripts/generate-tls-cert.sh
export CLEARFRAME_DOMAIN=${PUBLIC_DNS}
./scripts/generate-tls-cert.sh docker/certs
sudo docker build -t clearframe-stack:latest .
sudo docker-compose -f docker-compose.prod.yml --env-file .env.production up -d
REMOTE

echo ""
echo "=========================================="
echo " ClearFrame deployed successfully!"
echo "=========================================="
echo " URL:      ${HOST_URL}"
echo " Instance: ${INSTANCE_ID}"
echo " IP:       ${PUBLIC_IP}"
echo " SSH:      ssh -i ${KEY_FILE} ec2-user@${PUBLIC_IP}"
echo ""
echo " Login:    admin@erasys.local"
grep CLEARFRAME_ADMIN_PASSWORD "$ENV_FILE" | cut -d= -f2 | xargs -I{} echo " Password: {}"
echo ""
echo " Note: Browser will warn about self-signed TLS cert."
echo "       Point a domain at ${PUBLIC_IP} and run certbot for trusted HTTPS."
echo "=========================================="
