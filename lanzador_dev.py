"""
lanzador_dev.py — Simulador Chi.Bio Nexus (sin hardware)
=========================================================
Inicia el servidor de simulación y abre el navegador automáticamente.
Simula 3 reactores (M0, M1, M2) con datos biológicos realistas.

No requiere BeagleBone ni hardware Chi.Bio.

Uso:
    pip install -r requirements-windows.txt
    python lanzador_dev.py
"""

import webbrowser
import threading
import time

PORT = 5000
URL  = f"http://localhost:{PORT}"


def main():
    print("=" * 52)
    print("  Chi.Bio Nexus — Simulador (modo demo)")
    print("=" * 52)
    print(f"  Iniciando servidor en {URL} ...")

    # Import diferido: corre el servidor Flask embebido en este mismo
    # proceso (subprocess no funciona dentro de un .exe PyInstaller).
    import mock_server

    server_thread = threading.Thread(
        target=mock_server.app.run,
        kwargs={"debug": False, "host": "127.0.0.1", "port": PORT, "use_reloader": False},
        daemon=True,
    )
    server_thread.start()

    time.sleep(1.5)

    webbrowser.open(URL)
    print(f"  Navegador abierto en {URL}")
    print("  Presiona Ctrl+C para detener.\n")

    try:
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  Simulador detenido.")


if __name__ == "__main__":
    main()
