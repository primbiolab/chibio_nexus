# lanzador_camara.ps1 — Servidor de cámara WebRTC Chi.Bio Nexus (Windows)
# ─────────────────────────────────────────────────────────────────
# Prerrequisitos:
#   pip install -r requirements-windows.txt
#
# Uso:
#   .\scripts\lanzador_camara.ps1

$Root   = Split-Path $PSScriptRoot -Parent
$Script = Join-Path $Root "camera\server.py"
$Port   = 8000

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Chi.Bio Nexus - Servidor de Camara (WebRTC)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Accesible en: http://localhost:$Port"
Write-Host "  Verificar:    http://localhost:$Port/health"
Write-Host "  Detener con:  Ctrl+C"
Write-Host ""

if (-not (Test-Path $Script)) {
    Write-Host "ERROR: No se encontro camera\server.py" -ForegroundColor Red
    Write-Host "Asegurate de ejecutar este script desde la raiz del proyecto." -ForegroundColor Yellow
    exit 1
}

Push-Location $Root
try {
    python -m uvicorn camera.server:app --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
