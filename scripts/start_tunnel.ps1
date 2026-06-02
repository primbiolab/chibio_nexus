# Cloudflare Tunnel - Chi.Bio Nexus
$cloudflaredExe = "C:\Users\t r o n e x\Documents\cloudflared\cloudflared.exe"
$configFile     = "C:\Users\t r o n e x\Documents\cloudflared\config.yml"

if (-not (Test-Path $cloudflaredExe)) {
    Write-Error "No se encontro cloudflared.exe en: $cloudflaredExe"
    pause
    exit 1
}

if (-not (Test-Path $configFile)) {
    Write-Error "No se encontro config.yml en: $configFile"
    pause
    exit 1
}

Write-Host "Iniciando tunel Cloudflare..." -ForegroundColor Cyan
& $cloudflaredExe tunnel --config $configFile run
