# ─────────────────────────────────────────────────────────────
# compartir_red_beaglebone.ps1
# Comparte la red WiFi al BeagleBone Black via USB (Windows 10/11)
# Ejecutar como Administrador
#
# Los indices por defecto son los validados manualmente. El panel de
# control (lanzador_real.py) los detecta automaticamente y los pasa
# como parametros si encuentra adaptadores distintos.
# ─────────────────────────────────────────────────────────────

param(
    [int]$WifiIndex = 4,   # InterfaceIndex del adaptador WiFi (fuente de internet)
    [int]$UsbIndex  = 39   # InterfaceIndex del adaptador BeagleBone (Remote NDIS)
)

$INDEX_WIFI = $WifiIndex
$INDEX_USB  = $UsbIndex

Write-Host "Usando WifiIndex=$INDEX_WIFI UsbIndex=$INDEX_USB" -ForegroundColor DarkGray

# 1. Marcar la red WiFi como Privada (requisito para ICS)
Set-NetConnectionProfile -InterfaceIndex $INDEX_WIFI -NetworkCategory Private

# 2. Habilitar IP forwarding en ambas interfaces
Set-NetIPInterface -InterfaceIndex $INDEX_WIFI -Forwarding Enabled
Set-NetIPInterface -InterfaceIndex $INDEX_USB  -Forwarding Enabled

# 3. Forzar IP 192.168.7.1 en el adaptador USB (ICS la sobreescribe a 192.168.137.1)
$ip = (Get-NetIPAddress -InterfaceIndex $INDEX_USB -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress
if ($ip -ne '192.168.7.1') {
    if ($ip) { Remove-NetIPAddress -InterfaceIndex $INDEX_USB -IPAddress $ip -Confirm:$false }
    New-NetIPAddress -InterfaceIndex $INDEX_USB -IPAddress 192.168.7.1 -PrefixLength 24
}

Write-Host "Listo. Conecta por PuTTY a 192.168.7.2" -ForegroundColor Green
Start-Sleep 3
