# lanzador_camara.ps1 — Servidor de cámara Chi.Bio Nexus (Windows)
# ─────────────────────────────────────────────────────────────────
# Prerrequisitos:
#   pip install -r requirements-camera.txt
#
# Uso:
#   .\scripts\lanzador_camara.ps1

$Root   = Split-Path $PSScriptRoot -Parent
$Script = Join-Path $Root "camera\serverCamara.py"
$Port   = 5001

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Chi.Bio Nexus — Servidor de Camara (Windows)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Accesible en: http://localhost:$Port"
Write-Host "  Detener con:  Ctrl+C"
Write-Host ""

if (-not (Test-Path $Script)) {
    Write-Host "ERROR: No se encontro camera\serverCamara.py" -ForegroundColor Red
    Write-Host "Asegurate de ejecutar este script desde la raiz del proyecto." -ForegroundColor Yellow
    exit 1
}

python $Script
