# ─────────────────────────────────────────────────────────────
# instalar_servicios.ps1 — Instala ChibioCamera + ChibioTunnel como
# servicios Windows persistentes (NSSM) en un PC nuevo.
#
# Requiere: Ejecutar como Administrador.
# Requiere antes de correr este script:
#   - cloudflared.exe instalado (https://github.com/cloudflare/cloudflared)
#   - C:\Users\<usuario>\.cloudflared\config.yml + <tunnel-id>.json ya copiados
#     (son las credenciales del tunnel YA creado en Cloudflare, no se generan aqui)
#   - Python instalado, con las dependencias del proyecto (pip install -r ...)
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\pc\instalar_servicios.ps1
# ─────────────────────────────────────────────────────────────

param(
    [string]$CloudflaredExe = "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    # Raiz del proyecto clonado (donde vive camera/webrtc_server.py). Por defecto se
    # asume que este script vive en <proyecto>\scripts\, lo cual es cierto al
    # correrlo desde el repo. Si se invoca desde un .exe compilado (PyInstaller
    # extrae los .ps1 a una carpeta temporal, NO al repo real), hay que pasar
    # esta ruta explicitamente.
    [string]$ProyectoPath = (Split-Path -Parent $PSScriptRoot),
    # Si se pasa, no instala/toca el servicio ChibioTunnel ni exige cloudflared/config.yml.
    # Usar cuando el usuario eligio NO usar Cloudflare Tunnel (solo LAN).
    [switch]$SkipTunnel
)

$ErrorActionPreference = "Stop"

# ── 0. Verificar que corre como Administrador ──────────────────────
$esAdmin = ([Security.Principal.WindowsIdentity]::GetCurrent().Groups -contains "S-1-5-32-544")
if (-not $esAdmin) {
    Write-Error "Este script debe correrse como Administrador. Clic derecho -> 'Ejecutar como administrador'."
    exit 1
}

$proyecto   = $ProyectoPath
if (-not (Test-Path (Join-Path $proyecto "camera\webrtc_server.py"))) {
    Write-Error "No se encontro camera\webrtc_server.py en '$proyecto'. Pasa la ruta real del proyecto clonado con -ProyectoPath."
    exit 1
}
$cloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"

Write-Host "== Instalando servicios Chi.Bio Nexus (PC) ==" -ForegroundColor Cyan
Write-Host "Proyecto:    $proyecto" -ForegroundColor DarkGray
Write-Host "Cloudflared: $cloudflaredDir" -ForegroundColor DarkGray

# ── 1. NSSM ──────────────────────────────────────────────────────
function Find-NssmInWinget {
    Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*" `
        -Recurse -Filter "nssm.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "win64" } |
        Select-Object -First 1
}
$nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssmCmd) {
    $nssmExe = Find-NssmInWinget
    if ($nssmExe) { $env:PATH += ";$($nssmExe.DirectoryName)"; $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue }
}
if (-not $nssmCmd) {
    Write-Host "NSSM no encontrado. Instalando via winget..." -ForegroundColor Yellow
    winget install -e --id NSSM.NSSM --accept-source-agreements --accept-package-agreements --force
    $nssmExe = Find-NssmInWinget
    if ($nssmExe) { $env:PATH += ";$($nssmExe.DirectoryName)"; $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue }
    if (-not $nssmCmd) {
        Write-Error "No se pudo localizar nssm.exe tras instalar. Reabre PowerShell e intenta de nuevo."
        exit 1
    }
}
$nssm = $nssmCmd.Source
Write-Host "NSSM: $nssm" -ForegroundColor DarkGray

# ── 2. Python ────────────────────────────────────────────────────
# Preferimos el venv del proyecto (.venv, creado por instalar_todo.ps1) para
# que el servicio corra con las mismas librerias instaladas ahi, sin pisar
# ni depender del Python global del PC.
# OJO si hay que caer al Python del sistema: "Get-Command python" suele
# resolver al stub de WindowsApps (App Execution Alias), que falla al correr
# sin sesion interactiva (como hace NSSM bajo SYSTEM). Usamos "py" (Python
# Launcher) para encontrar el interprete REAL.
$venvPython = Join-Path $proyecto ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = $null
    try {
        $python = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim()
    } catch {}
    if (-not $python -or -not (Test-Path $python) -or $python -like "*WindowsApps*") {
        Write-Error "No se pudo resolver un Python real (no-stub). Instala Python desde python.org y reintenta."
        exit 1
    }
}
Write-Host "Python: $python" -ForegroundColor DarkGray

# ── 3. cloudflared.exe + config.yml (solo si se va a usar el tunel) ─
if (-not $SkipTunnel) {
    if (-not (Test-Path $CloudflaredExe)) {
        $alt = Get-Command cloudflared -ErrorAction SilentlyContinue
        if ($alt) { $CloudflaredExe = $alt.Source }
    }
    if (-not (Test-Path $CloudflaredExe)) {
        Write-Error "cloudflared.exe no encontrado en '$CloudflaredExe'. Instalalo o pasa -CloudflaredExe <ruta>."
        exit 1
    }
    if (-not (Test-Path (Join-Path $cloudflaredDir "config.yml"))) {
        Write-Error "No existe $cloudflaredDir\config.yml. Copia el config.yml y el .json de credenciales del tunnel antes de continuar."
        exit 1
    }
    Write-Host "cloudflared.exe: $CloudflaredExe" -ForegroundColor DarkGray
} else {
    Write-Host "Tunel Cloudflare omitido (-SkipTunnel)" -ForegroundColor DarkGray
}

# ── Helper: crear o reconfigurar un servicio NSSM (idempotente) ──
function Instalar-ServicioNssm {
    param(
        [string]$Nombre,
        [string]$Exe,
        [string]$Parametros,
        [string]$Directorio
    )

    $existe = Get-Service -Name $Nombre -ErrorAction SilentlyContinue
    if ($existe) {
        Write-Host "  $Nombre ya existe -> deteniendo para reconfigurar..." -ForegroundColor Yellow
        Stop-Service -Name $Nombre -ErrorAction SilentlyContinue
    } else {
        & $nssm install $Nombre $Exe | Out-Null
    }

    & $nssm set $Nombre Application       $Exe         | Out-Null
    & $nssm set $Nombre AppParameters     $Parametros  | Out-Null
    & $nssm set $Nombre AppDirectory      $Directorio  | Out-Null
    & $nssm set $Nombre Start             SERVICE_AUTO_START | Out-Null
    & $nssm set $Nombre AppExit Default   Restart      | Out-Null
    & $nssm set $Nombre AppRestartDelay   3000         | Out-Null
    & $nssm set $Nombre AppStdout         (Join-Path $Directorio "$Nombre.out.log") | Out-Null
    & $nssm set $Nombre AppStderr         (Join-Path $Directorio "$Nombre.err.log") | Out-Null

    Start-Service $Nombre
    Start-Sleep -Seconds 2
    $estado = (Get-Service $Nombre).Status
    if ($estado -eq "Running") {
        Write-Host "  $Nombre -> OK ($estado)" -ForegroundColor Green
    } else {
        Write-Host "  $Nombre -> $estado (revisar $Directorio\$Nombre.err.log)" -ForegroundColor Red
    }
}

# ── 4. ChibioCamera ──────────────────────────────────────────────
Write-Host "`n-- ChibioCamera --" -ForegroundColor Cyan
Instalar-ServicioNssm -Nombre "ChibioCamera" -Exe $python `
    -Parametros "-m uvicorn camera.webrtc_server:app --host 0.0.0.0 --port 8000" `
    -Directorio $proyecto

# ── 5. ChibioTunnel (solo si se va a usar el tunel) ──────────────
if (-not $SkipTunnel) {
    Write-Host "`n-- ChibioTunnel --" -ForegroundColor Cyan
    Instalar-ServicioNssm -Nombre "ChibioTunnel" -Exe $CloudflaredExe `
        -Parametros "tunnel --config config.yml run" `
        -Directorio $cloudflaredDir

    # ── 6. DNS route: garantiza que el CNAME en Cloudflare apunte a este tunnel ─
    # Extrae tunnel ID de config.yml y hostname de config_pc.py.
    # --overwrite-dns sobreescribe cualquier A/CNAME anterior (evita el error
    # "record with that host already exists" si se reinstala o cambia de tunnel).
    $configYml  = Join-Path $cloudflaredDir "config.yml"
    $configPc   = Join-Path $proyecto "config_pc.py"
    $tunnelId   = $null
    $chiHostname = $null

    if (Test-Path $configYml) {
        $tunnelId = (Select-String -Path $configYml -Pattern "^tunnel:\s*(\S+)").Matches[0].Groups[1].Value
    }
    $camHostname = $null
    if (Test-Path $configPc) {
        $chiHostname = (Select-String -Path $configPc -Pattern 'CHIBIO_HOSTNAME\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
        $camHostname = (Select-String -Path $configPc -Pattern 'CAMERA_HOSTNAME\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
    }

    foreach ($h in @($chiHostname, $camHostname)) {
        if ($tunnelId -and $h) {
            Write-Host "`n-- DNS route: $h -> tunnel $tunnelId --" -ForegroundColor Cyan
            & $CloudflaredExe tunnel route dns --overwrite-dns $tunnelId $h 2>&1 | Write-Host
        } elseif (-not $h) {
            Write-Warning "Hostname vacio, omitiendo DNS route. Crealo manualmente: cloudflared tunnel route dns --overwrite-dns <tunnel-id> <hostname>"
        }
    }

    Write-Host "`nListo. Verifica con: Get-Service ChibioCamera, ChibioTunnel" -ForegroundColor Green
} else {
    Write-Host "`nListo. Verifica con: Get-Service ChibioCamera" -ForegroundColor Green
}
