#!/bin/sh
set -e
mkdir -p "$CLEARFRAME_DATA_DIR"
cd /app/backend
exec python run.py
