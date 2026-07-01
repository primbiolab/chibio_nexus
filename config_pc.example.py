# config_pc.py — Configuracion de Cloudflare Tunnel para ESTE PC
# ================================================================
# Copia este archivo a config_pc.py (mismo lugar) y completa con tus
# propios datos antes de usar el tunel Cloudflare.
#
# Si NO vas a usar Cloudflare Tunnel (solo quieres acceder a Chi.Bio
# Nexus en tu red local), no necesitas crear este archivo — el panel
# de control y instalar_todo.ps1 te van a preguntar y pueden saltarse
# todo lo relacionado con el tunel.
#
# config_pc.py nunca se sube a git (esta en .gitignore) — cada persona
# pone aqui SU PROPIO dominio y nombre de tunel, no el de otra.

TUNNEL_NAME = "mi-tunel"
CHIBIO_HOSTNAME = "mi-dominio.com"
CAMERA_HOSTNAME = "mi-camara.com"
