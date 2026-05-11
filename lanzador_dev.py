"""
lanzador_dev.py — Simulador Chi.Bio Nexus (sin hardware)
=========================================================
Inicia el servidor de simulación y abre el navegador automáticamente.
Simula 3 reactores (M0, M1, M2) con datos biológicos realistas.

No requiere BeagleBone ni hardware Chi.Bio.

Uso:
    pip install -r requirements-dev.txt
    python lanzador_dev.py
"""

import subprocess
import webbrowser
import time
import sys
import os

PORT = 5000
URL  = f"http://localhost:{PORT}"
ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print("=" * 52)
    print("  Chi.Bio Nexus — Simulador (modo demo)")
    print("=" * 52)
    print(f"  Iniciando servidor en {URL} ...")

    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "mock_server.py")],
        cwd=ROOT,
    )

    time.sleep(1.5)

    webbrowser.open(URL)
    print(f"  Navegador abierto en {URL}")
    print("  Presiona Ctrl+C para detener.\n")

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\n  Simulador detenido.")


if __name__ == "__main__":
    main()
