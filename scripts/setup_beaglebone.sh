#!/bin/bash
# setup_beaglebone.sh — Instalación inicial de Chi.Bio Nexus en BeagleBone Black
#
# Uso (desde /root/chibio en la BeagleBone):
#   bash scripts/setup_beaglebone.sh

set -e

CHIBIO_DIR="/root/chibio"

echo "========================================"
echo "  Chi.Bio Nexus — Setup BeagleBone"
echo "========================================"

cd "$CHIBIO_DIR"

# 1. Dependencias Python
echo ""
echo "[1/3] Instalando dependencias Python..."
pip install -r requirements.txt
echo "  ✓ Dependencias instaladas"

# 2. Configuración de API key
echo ""
echo "[2/3] Configurando API key de Gemini..."
if [ ! -f config.py ]; then
    cp config.example.py config.py
    echo "  ✓ config.py creado"
    echo "  ⚠  IMPORTANTE: edita config.py con tu API key de Gemini:"
    echo "       nano $CHIBIO_DIR/config.py"
else
    echo "  ✓ config.py ya existe"
fi

# 3. Archivo de protocolo inicial
echo ""
echo "[3/3] Verificando protocolo..."
if [ ! -f protocolo.py ]; then
    echo "# protocolo.py — generado por Chi.Bio Nexus" > protocolo.py
    echo "  ✓ protocolo.py vacío creado"
else
    echo "  ✓ protocolo.py ya existe"
fi

echo ""
echo "========================================"
echo "  Setup completo."
echo "  Inicia el servidor con:"
echo "    bash scripts/cb.sh"
echo "========================================"
