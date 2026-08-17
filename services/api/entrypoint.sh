#!/bin/sh
set -e
DATA_DIR="${CLEARFRAME_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"
export CLEARFRAME_API_PORT="${PORT:-${CLEARFRAME_API_PORT:-8080}}"
exec python run.py
