# desactivar_servicios_pc.ps1 — Detiene los servicios NSSM del PC (camara + tunel)
# Requiere ejecutarse elevado (el lanzador lo invoca via Start-Process -Verb RunAs)

$ErrorActionPreference = "Continue"

Write-Host "Deteniendo servicios Chi.Bio Nexus (PC)..." -ForegroundColor Cyan

foreach ($svc in @("ChibioCamera", "ChibioTunnel")) {
    try {
        $s = Get-Service -Name $svc -ErrorAction Stop
        if ($s.Status -eq "Running") {
            Stop-Service -Name $svc -ErrorAction Stop
        }
        Write-Host "  $svc -> detenido" -ForegroundColor Green
    } catch {
        Write-Host "  $svc -> ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Start-Sleep -Seconds 2
Write-Host "Listo." -ForegroundColor Green
Start-Sleep -Seconds 2
