# ─────────────────────────────────────────────────────────────
# compartir_red_beaglebone.ps1
# Comparte la red WiFi al BeagleBone Black via USB (Windows 10/11)
# Ejecutar como Administrador
# ─────────────────────────────────────────────────────────────

$INDEX_WIFI = 18  # InterfaceIndex del adaptador WiFi (fuente de internet)
$INDEX_USB  = 15  # InterfaceIndex del adaptador BeagleBone (Remote NDIS)

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
