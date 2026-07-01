# ─────────────────────────────────────────────────────────────
# instalar_todo.ps1 — Setup completo de Chi.Bio Nexus en un PC nuevo (Windows)
# Orquesta TODO lo que antes eran pasos manuales / scripts separados:
#   1. Dependencias Python (requirements-windows.txt)
#   2. config.py (Gemini API key)
#   3. NSSM
#   4. cloudflared.exe (descarga si falta)
#   5. Login Cloudflare (UNICO paso manual: abre navegador, requiere cuenta)
#   6. Crear tunel (si no existe)
#   7. Generar ~/.cloudflared/config.yml
#   8. Apuntar DNS (chibio.* y camera.*) al tunel
#   9. Instalar servicios NSSM persistentes (ChibioCamera, ChibioTunnel)
#  10. Detectar adaptadores de red y compartir WiFi -> BBB por USB (ICS)
#
# Reentrante: cada paso detecta si ya esta hecho y lo salta. Correrlo de
# nuevo en un PC ya configurado no rompe nada.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_todo.ps1
# ─────────────────────────────────────────────────────────────

param(
    # Sin defaults propios: cada quien usa SU dominio/tunel. Si no se pasan,
    # se leen de config_pc.py (en la raiz del proyecto) si existe.
    [string]$TunnelName      = "",
    [string]$ChibioHostname  = "",
    [string]$CameraHostname  = "",
    [string]$CloudflaredDir  = (Join-Path $env:USERPROFILE "Documents\cloudflared"),
    [switch]$SkipRed,     # saltar el paso de red ICS (util en PCs sin BBB conectada)
    [switch]$SkipTunnel,  # no usar Cloudflare Tunnel (solo acceso LAN)
    # Raiz del proyecto clonado. Por defecto asume que este script vive en
    # <proyecto>\scripts\ (cierto al correr desde el repo). Si se invoca desde
    # un .exe compilado (PyInstaller extrae los .ps1 a una carpeta temporal,
    # NO al repo real), el lanzador debe pasar esta ruta explicitamente.
    [string]$ProyectoPath = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"

trap {
    Write-Host "`n[ERROR] $_" -ForegroundColor Red
    Write-Host ""
    Read-Host "Presiona Enter para cerrar"
    exit 1
}

$proyecto = $ProyectoPath
if (-not (Test-Path (Join-Path $proyecto "requirements-windows.txt"))) {
    throw "No se encontro requirements-windows.txt en '$proyecto'. Pasa la ruta real del proyecto clonado con -ProyectoPath."
}
$cfDir    = Join-Path $env:USERPROFILE ".cloudflared"

function Step($n, $title) { Write-Host "`n== [$n/10] $title ==" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  OK: $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "  $msg" -ForegroundColor DarkGray }

# cloudflared escribe warnings normales (ej. "version outdated") a stderr.
# Con $ErrorActionPreference="Stop" global, PowerShell trata esos warnings
# como excepcion terminal y mata el script. Por eso TODA llamada nativa a
# cloudflared pasa por aqui: baja a "Continue" solo para esa llamada y
# devuelve stdout ya limpio (al llamador le toca revisar $LASTEXITCODE si
# quiere saber si realmente fallo).
function Invoke-Cloudflared {
    param([string]$Exe, [string[]]$ArgsList)
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $salida = & $Exe @ArgsList 2>$null
    $ErrorActionPreference = $prevEAP
    return $salida
}

# ── config_pc.py: si no se pasaron por parametro, usar lo que haya ahi ──
# (cada persona pone su propio dominio/tunel en config_pc.py, gitignored;
#  ver config_pc.example.py para el formato)
if (-not $SkipTunnel -and (-not $TunnelName -or -not $ChibioHostname -or -not $CameraHostname)) {
    $configPcPath = Join-Path $proyecto "config_pc.py"
    if (Test-Path $configPcPath) {
        $contenido = Get-Content $configPcPath -Raw
        function Leer-ValorConfig($contenido, $clave) {
            if ($contenido -match "$clave\s*=\s*[`"']([^`"']+)[`"']") { return $Matches[1] }
            return $null
        }
        if (-not $TunnelName)     { $TunnelName     = Leer-ValorConfig $contenido "TUNNEL_NAME" }
        if (-not $ChibioHostname) { $ChibioHostname = Leer-ValorConfig $contenido "CHIBIO_HOSTNAME" }
        if (-not $CameraHostname) { $CameraHostname = Leer-ValorConfig $contenido "CAMERA_HOSTNAME" }
    }
}
if (-not $SkipTunnel -and (-not $TunnelName -or -not $ChibioHostname -or -not $CameraHostname)) {
    throw ("Falta configurar el tunel Cloudflare: copia 'config_pc.example.py' a 'config_pc.py' " +
        "y completa TUNNEL_NAME/CHIBIO_HOSTNAME/CAMERA_HOSTNAME con tus propios datos, " +
        "o pasa -TunnelName/-ChibioHostname/-CameraHostname, o usa -SkipTunnel si no vas a usar Cloudflare Tunnel.")
}

# ── 0. Re-lanzar elevado (NSSM, servicios e ICS necesitan admin) ────────
$esAdmin = ([Security.Principal.WindowsIdentity]::GetCurrent().Groups -contains "S-1-5-32-544")
if (-not $esAdmin) {
    Write-Host "Este script necesita permisos de Administrador. Re-lanzando..." -ForegroundColor Yellow
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -ProyectoPath `"$proyecto`""
    if ($SkipRed)    { $argList += " -SkipRed" }
    if ($SkipTunnel) { $argList += " -SkipTunnel" }
    if ($TunnelName)      { $argList += " -TunnelName `"$TunnelName`"" }
    if ($ChibioHostname)  { $argList += " -ChibioHostname `"$ChibioHostname`"" }
    if ($CameraHostname)  { $argList += " -CameraHostname `"$CameraHostname`"" }
    Start-Process powershell -ArgumentList $argList -Verb RunAs -Wait
    exit
}

Write-Host "== Chi.Bio Nexus — Setup completo (PC) ==" -ForegroundColor Cyan
Write-Host "Proyecto: $proyecto`n" -ForegroundColor DarkGray

# ── 1. Python + entorno virtual + dependencias ───────────────────────────
Step 1 "Python + entorno virtual + dependencias"
$pySistema = $null
try { $pySistema = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim() } catch {}
if (-not $pySistema -or -not (Test-Path $pySistema) -or $pySistema -like "*WindowsApps*") {
    throw "Python no encontrado (real, no stub). Instala desde https://python.org y reintenta."
}
Info "Python del sistema: $pySistema"

$venvDir = Join-Path $proyecto ".venv"
$python  = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $python)) {
    Info "Creando entorno virtual en $venvDir (evita conflictos con otras librerias del PC)..."
    & $pySistema -m venv $venvDir
    if (-not (Test-Path $python)) {
        throw "No se pudo crear el entorno virtual en $venvDir."
    }
} else {
    Ok "Entorno virtual ya existe en $venvDir"
}

& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r (Join-Path $proyecto "requirements-windows.txt")
Ok "Dependencias instaladas en el venv ($python)"

# ── 2. config.py (Gemini API key) ───────────────────────────────────────
Step 2 "config.py (Gemini API key)"
$configPath = Join-Path $proyecto "config.py"
if (Test-Path $configPath) {
    Ok "config.py ya existe, no se toca"
} else {
    Write-Host "  No tienes config.py todavia." -ForegroundColor Yellow
    Write-Host "  Consigue tu key en: https://aistudio.google.com/apikey" -ForegroundColor Yellow
    $key = Read-Host "  Pega tu GEMINI_API_KEY (Enter para dejarla como placeholder)"
    if (-not $key) { $key = "your_gemini_api_key_here" }
    $key = $key -replace '"', '\"' -replace "'", "\'"
    "GEMINI_API_KEY = `"$key`"" | Set-Content -Path $configPath -Encoding UTF8
    Ok "config.py creado"
}

# ── 3. NSSM ──────────────────────────────────────────────────────────────
Step 3 "NSSM"
function Find-NssmInWinget {
    Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*" `
        -Recurse -Filter "nssm.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "win64" } |
        Select-Object -First 1
}
$nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssmCmd) {
    # PATH puede no tener nssm aunque winget lo instalo antes — buscar primero en disco
    $nssmExe = Find-NssmInWinget
    if ($nssmExe) {
        $env:PATH += ";$($nssmExe.DirectoryName)"
        $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    }
}
if (-not $nssmCmd) {
    Info "No encontrado, instalando via winget..."
    # --force reinstala aunque winget crea que ya esta (util si los archivos fueron borrados)
    winget install -e --id NSSM.NSSM --accept-source-agreements --accept-package-agreements --force
    $nssmExe = Find-NssmInWinget
    if ($nssmExe) {
        $env:PATH += ";$($nssmExe.DirectoryName)"
        $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    }
    if (-not $nssmCmd) {
        throw "No se pudo localizar nssm.exe tras instalar. Reabre PowerShell y reintenta."
    }
}
Ok "NSSM: $($nssmCmd.Source)"

if (-not $SkipTunnel) {

# ── 4. cloudflared.exe ───────────────────────────────────────────────────
Step 4 "cloudflared.exe"
$cloudflaredExe = Join-Path $CloudflaredDir "cloudflared.exe"
if (-not (Test-Path $cloudflaredExe)) {
    Info "No encontrado, descargando ultima version..."
    New-Item -ItemType Directory -Force -Path $CloudflaredDir | Out-Null
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cloudflaredExe
}
Ok "cloudflared.exe: $cloudflaredExe"

# ── 5. Login Cloudflare (UNICO paso manual de todo el setup) ────────────
Step 5 "Login Cloudflare"
$certPem = Join-Path $cfDir "cert.pem"
if (Test-Path $certPem) {
    Ok "Ya autenticado (cert.pem existe)"
} else {
    Write-Host "  Se va a abrir el navegador. Inicia sesion en tu cuenta de Cloudflare y autoriza tu dominio." -ForegroundColor Yellow
    Invoke-Cloudflared -Exe $cloudflaredExe -ArgsList @("tunnel", "login") | ForEach-Object { Info $_ }
    if (-not (Test-Path $certPem)) {
        throw "Login no se completo (no aparecio cert.pem). Reintenta el script."
    }
    Ok "Login completado"
}

# ── 6. Crear (o reusar) el tunel ─────────────────────────────────────────
Step 6 "Tunel '$TunnelName'"
function Get-TunnelId($nombre) {
    $raw = Invoke-Cloudflared -Exe $cloudflaredExe -ArgsList @("tunnel", "list", "--output", "json")
    $lista = $raw | ConvertFrom-Json
    if ($lista) {
        $match = $lista | Where-Object { $_.name -eq $nombre }
        if ($match) { return $match.id }
    }
    return $null
}
$tunnelId = Get-TunnelId $TunnelName
if ($tunnelId) {
    Ok "Tunel ya existe (id=$tunnelId)"
} else {
    Info "Creando tunel..."
    Invoke-Cloudflared -Exe $cloudflaredExe -ArgsList @("tunnel", "create", $TunnelName) | ForEach-Object { Info $_ }
    $tunnelId = Get-TunnelId $TunnelName
    if (-not $tunnelId) {
        throw "No se pudo crear/leer el tunel '$TunnelName'."
    }
    Ok "Tunel creado (id=$tunnelId)"
}
$credFile = Join-Path $cfDir "$tunnelId.json"
if (-not (Test-Path $credFile)) {
    throw "Falta el archivo de credenciales $credFile. Si perdiste las credenciales, borra el tunel ($($cloudflaredExe) tunnel delete $TunnelName) y vuelve a correr este script."
}

# ── 7. Generar config.yml (en ~/.cloudflared, donde lo lee el servicio) ─
Step 7 "config.yml"
$configYml = Join-Path $cfDir "config.yml"
if (Test-Path $configYml) {
    Ok "config.yml ya existe, no se sobreescribe (editalo a mano si necesitas cambiar algo)"
} else {
@"
tunnel: $tunnelId
credentials-file: '$credFile'

ingress:
  - hostname: $ChibioHostname
    service: http://192.168.7.2:5000

  - hostname: $CameraHostname
    service: http://127.0.0.1:8000

  - service: http_status:404
"@ | Set-Content -Path $configYml -Encoding UTF8
    Ok "config.yml creado en $configYml"
}

# ── 8. DNS -> tunel ───────────────────────────────────────────────────────
Step 8 "DNS"
Invoke-Cloudflared -Exe $cloudflaredExe -ArgsList @("tunnel", "route", "dns", $TunnelName, $ChibioHostname) | ForEach-Object { Info $_ }
if ($LASTEXITCODE -ne 0) { Write-Host "  WARN: DNS para $ChibioHostname puede no haberse configurado (exit $LASTEXITCODE)" -ForegroundColor Yellow }
Invoke-Cloudflared -Exe $cloudflaredExe -ArgsList @("tunnel", "route", "dns", $TunnelName, $CameraHostname) | ForEach-Object { Info $_ }
if ($LASTEXITCODE -ne 0) { Write-Host "  WARN: DNS para $CameraHostname puede no haberse configurado (exit $LASTEXITCODE)" -ForegroundColor Yellow }
Ok "DNS verificado/apuntado"

} else {
    Write-Host "`n== [4-8/10] Cloudflare Tunnel omitido (-SkipTunnel) ==" -ForegroundColor Cyan
    Info "Solo acceso LAN — abre http://192.168.7.2:5000 directamente en tu red."
}

# ── 9. Servicios NSSM persistentes ───────────────────────────────────────
if ($SkipTunnel) {
    Step 9 "Servicios NSSM (ChibioCamera)"
    & (Join-Path $PSScriptRoot "instalar_servicios.ps1") -ProyectoPath $proyecto -SkipTunnel
} else {
    Step 9 "Servicios NSSM (ChibioCamera, ChibioTunnel)"
    & (Join-Path $PSScriptRoot "instalar_servicios.ps1") -CloudflaredExe $cloudflaredExe -ProyectoPath $proyecto
}

# ── 10. Red compartida PC -> BBB (USB/ICS) ───────────────────────────────
Step 10 "Red compartida PC -> BBB (USB/ICS)"
if ($SkipRed) {
    Info "Saltado (-SkipRed)"
} else {
    $adaptadores = Get-NetAdapter | Select-Object Name, ifIndex, InterfaceDescription, Status
    $wifiCand = $adaptadores | Where-Object { $_.InterfaceDescription -match "wireless|wi-?fi|802\.11|wlan" }
    $usbCand  = $adaptadores | Where-Object { $_.InterfaceDescription -match "remote ndis|rndis|usb ethernet|linux usb|cdc ether" }
    $wifiUp = $wifiCand | Where-Object { $_.Status -eq "Up" }
    $usbUp  = $usbCand  | Where-Object { $_.Status -eq "Up" }
    if ($wifiUp) { $wifiCand = $wifiUp }
    if ($usbUp)  { $usbCand  = $usbUp }

    if ($wifiCand.Count -eq 1 -and $usbCand.Count -eq 1) {
        $wifiIdx = $wifiCand[0].ifIndex
        $usbIdx  = $usbCand[0].ifIndex
        Info "WiFi detectado: ifIndex=$wifiIdx | BBB (USB) detectado: ifIndex=$usbIdx"
        & (Join-Path $PSScriptRoot "compartir_red_beaglebone.ps1") -WifiIndex $wifiIdx -UsbIndex $usbIdx
    } else {
        Write-Host "  No se detecto exactamente 1 adaptador WiFi y 1 USB(BBB)." -ForegroundColor Yellow
        Write-Host "  WiFi candidatos: $($wifiCand.Count) | USB candidatos: $($usbCand.Count)" -ForegroundColor Yellow
        Write-Host "  Conecta la BBB por USB y corre a mano:" -ForegroundColor Yellow
        Write-Host "    .\scripts\compartir_red_beaglebone.ps1 -WifiIndex <N> -UsbIndex <N>" -ForegroundColor Yellow
    }
}

Write-Host "`n== Setup completo ==" -ForegroundColor Green
Write-Host "Verifica con: Get-Service ChibioCamera, ChibioTunnel" -ForegroundColor DarkGray
Write-Host "Pendiente manual (dentro de la BBB, no automatizable): conectar por PuTTY, correr ruta+DNS, arrancar cb.sh." -ForegroundColor Yellow
Write-Host ""
Read-Host "Presiona Enter para cerrar"
