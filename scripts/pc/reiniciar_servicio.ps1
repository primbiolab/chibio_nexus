# reiniciar_servicio.ps1 -Servicio <nombre>
# Reinicia UN servicio NSSM puntual (ChibioCamera o ChibioTunnel).
# Requiere ejecutarse elevado (el lanzador lo invoca via Start-Process -Verb RunAs).

param(
    [Parameter(Mandatory = $true)]
    [string]$Servicio
)

$ErrorActionPreference = "Continue"

Write-Host "Reiniciando $Servicio..." -ForegroundColor Cyan

try {
    $s = Get-Service -Name $Servicio -ErrorAction Stop
    if ($s.Status -eq "Running") {
        Stop-Service -Name $Servicio -ErrorAction Stop
        Write-Host "  Detenido." -ForegroundColor DarkGray
    }
    Start-Service -Name $Servicio -ErrorAction Stop
    Write-Host "  $Servicio -> OK (Running)" -ForegroundColor Green
} catch {
    Write-Host "  ERROR reiniciando $Servicio : $($_.Exception.Message)" -ForegroundColor Red
}

Start-Sleep -Seconds 2
Write-Host "Listo." -ForegroundColor Green
Start-Sleep -Seconds 2
