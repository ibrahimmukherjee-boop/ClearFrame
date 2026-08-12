#!/usr/bin/env bash
# On-host watchdog: keep Docker stack healthy after reboots or crashes.
# Installed on EC2 via deploy-minimal-ec2.sh (cron every 5 minutes).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/clearframe/app}"
LOG="${LOG:-/var/log/clearframe-watchdog.log}"

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

if ! curl -sf --connect-timeout 5 http://localhost/api/health 2>/dev/null | grep -q '"status":"ok"'; then
  log "Health check failed — restarting stack"
  cd "$APP_DIR" || exit 0
  if sudo docker compose version >/dev/null 2>&1; then
    DC="sudo docker compose"
  else
    DC="sudo docker-compose"
  fi
  $DC -f docker-compose.minimal.yml --env-file .env.production up -d >> "$LOG" 2>&1 || true
  sleep 15
  if curl -sf --connect-timeout 5 http://localhost/api/health 2>/dev/null | grep -q '"status":"ok"'; then
    log "Stack recovered"
  else
    log "Stack still unhealthy after restart"
  fi
fi
