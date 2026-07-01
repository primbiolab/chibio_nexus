# compilar.ps1 — Genera los .exe de Chi.Bio Nexus con PyInstaller
# ==================================================================
# Produce dos ejecutables en la raiz del proyecto:
#   ChiBioNexus-Demo.exe  -> mock_server.py (simulador, sin hardware)
#   ChiBioNexus-Real.exe  -> panel de control PC: red ICS, servicios NSSM, verificacion
#
# ChiBioNexus-Real.exe puede colocarse en cualquier carpeta; requirements-windows.txt
# viene embebido y se extrae junto al .exe la primera vez que se corre "Instalar todo".
#
# Uso:
#   pip install pyinstaller flask
#   .\compilar.ps1

$root = $PSScriptRoot
$iconLegacy = "$root\assets\nexus.ico"
$iconBlanco = "$root\assets\logo_blanco.ico"

try {
    python -m PyInstaller --version | Out-Null
} catch {
    Write-Error "PyInstaller no encontrado. Ejecuta: pip install pyinstaller"
    exit 1
}

Write-Host "== Generando logo_blanco.ico desde logo.png ==" -ForegroundColor Cyan
python -c "
from PIL import Image
import sys
try:
    img = Image.open(r'$root\assets\logo.png').convert('RGBA')
    img.save(r'$iconBlanco', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print('  OK: logo_blanco.ico generado')
except Exception as e:
    print(f'  WARN: no se pudo generar logo_blanco.ico: {e}')
    sys.exit(1)
"
if (-not $?) {
    Write-Host "  Usando nexus.ico como fallback" -ForegroundColor Yellow
    $iconBlanco = $iconLegacy
}

Write-Host "== Compilando ChiBioNexus-Demo.exe (mock_server + UI) ==" -ForegroundColor Cyan
python -m PyInstaller --onefile `
    --name "ChiBioNexus-Demo" `
    --icon $iconLegacy `
    --distpath "$root" `
    --add-data "templates;templates" `
    --add-data "static;static" `
    --hidden-import flask `
    "$root\lanzador_dev.py"

Write-Host "== Compilando ChiBioNexus-Real.exe (panel de control PC) ==" -ForegroundColor Cyan
python -m PyInstaller --onefile --noconsole `
    --name "ChiBioNexus-Real" `
    --icon $iconBlanco `
    --distpath "$root" `
    --add-data "assets\nexus.ico;assets" `
    --add-data "assets\logo.png;assets" `
    --add-data "assets\logo_negro.png;assets" `
    --add-data "requirements-windows.txt;." `
    --add-data "scripts\pc\compartir_red_beaglebone.ps1;scripts\pc" `
    --add-data "scripts\pc\activar_servicios_pc.ps1;scripts\pc" `
    --add-data "scripts\pc\desactivar_servicios_pc.ps1;scripts\pc" `
    --add-data "scripts\pc\instalar_todo.ps1;scripts\pc" `
    --add-data "scripts\pc\instalar_servicios.ps1;scripts\pc" `
    --add-data "scripts\pc\reiniciar_servicio.ps1;scripts\pc" `
    "$root\lanzador_real.py"

Write-Host ""
Write-Host "Listo. Ejecutables en la raiz del proyecto:" -ForegroundColor Green
Write-Host "  - ChiBioNexus-Demo.exe"
Write-Host "  - ChiBioNexus-Real.exe"
