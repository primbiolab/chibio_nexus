#!/bin/bash
# cb.sh — Inicia Chi.Bio Nexus en la BeagleBone Black
# Uso: bash scripts/cb.sh

set -e

CHIBIO_DIR="/root/chibio"
HOST="192.168.7.2"
PORT="5000"

cd "$CHIBIO_DIR"

echo "=== Chi.Bio Nexus ==="
echo "Iniciando servidor en http://$HOST:$PORT ..."

exec gunicorn \
    --bind "$HOST:$PORT" \
    --workers 1 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    app:application
