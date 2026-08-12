#!/usr/bin/env bash
# Start the demo EC2 if stopped and verify the app health endpoint.
# Run manually, from CI, or on a schedule (e.g. cron every 15 min on your laptop).
set -euo pipefail

INSTANCE_ID="${INSTANCE_ID:-i-08d17d775371f32f1}"
REGION="${AWS_REGION:-us-east-1}"

STATE=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text)

if [ "$STATE" = "stopped" ] || [ "$STATE" = "stopping" ]; then
  echo "==> Instance ${INSTANCE_ID} is ${STATE} — starting..."
  aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null
  aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
  echo "    Instance running"
elif [ "$STATE" != "running" ]; then
  echo "Instance state: ${STATE} (cannot auto-recover)"
  exit 1
else
  echo "==> Instance ${INSTANCE_ID} already running"
fi

PUBLIC_IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
PUBLIC_DNS=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)

for i in $(seq 1 12); do
  if curl -sf --connect-timeout 5 "http://${PUBLIC_IP}/api/health" | grep -q '"status":"ok"'; then
    echo "==> Health OK — http://${PUBLIC_IP}"
    echo "    DNS: http://${PUBLIC_DNS}"
    exit 0
  fi
  sleep 10
done

echo "WARN: Instance running but /api/health not OK yet — check Docker on host"
exit 1
