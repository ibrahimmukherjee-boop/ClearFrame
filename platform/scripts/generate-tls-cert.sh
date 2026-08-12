#!/bin/bash
# Generate self-signed TLS cert with DNS + IP SAN for EC2
set -e
CERT_DIR="${1:-./docker/certs}"
mkdir -p "$CERT_DIR"
DOMAIN="${CLEARFRAME_DOMAIN:-clearframe.local}"
IP="${CLEARFRAME_IP:-}"

FORCE="${CLEARFRAME_REGEN_CERT:-false}"
if [ "$FORCE" = "true" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
  SAN="DNS:${DOMAIN}"
  [ -n "$IP" ] && SAN="${SAN},IP:${IP}"
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=${DOMAIN}/O=ClearFrame/C=US" \
    -addext "subjectAltName=${SAN}"
  echo "Generated cert for ${DOMAIN}${IP:+ + ${IP}} in ${CERT_DIR}"
fi
