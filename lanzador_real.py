"""
lanzador_real.py — Panel de Control Chi.Bio Nexus (PC, hardware real)
======================================================================
No corre ningun servidor Flask local. El servidor real vive en la
BeagleBone (192.168.7.2:5000) o detras del tunel de Cloudflare
(https://chibio.primbiolab.org).

Este panel orquesta y verifica SOLO la parte del proceso que vive en
el PC Windows:
  1. Compartir la red WiFi a la BBB via USB/ICS (compartir_red_beaglebone.ps1)
  2. Iniciar/detener los servicios NSSM persistentes (ChibioCamera, ChibioTunnel)
  3. Verificar el estado real de los 4 eslabones: red compartida, server BBB,
     camara local, tunel Cloudflare

Los pasos que viven DENTRO de la BeagleBone (SSH/PuTTY, los 3 comandos de
ruta+DNS, arrancar cb.sh) NO se automatizan aqui — requieren credenciales
SSH que este panel no maneja. El panel los recuerda en pantalla y solo
puede *verificar* su resultado desde afuera (TCP/HTTP).

UI: CustomTkinter (esquinas redondeadas, hover) + navegacion por paginas
(rail de iconos a la izquierda) en vez de una sola columna larga con scroll.

Pensado para empacarse con PyInstaller como .exe de doble clic
(ver compilar.ps1 -> ChiBioNexus-Real.exe).

Uso:
    python lanzador_real.py
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

LOCAL_HOST = "127.0.0.1"  # TEMP: mock — cambiar a "192.168.7.2" para BBB real
LOCAL_PORT = 5000
LOCAL_URL = f"http://{LOCAL_HOST}:{LOCAL_PORT}"

CAMERA_LOCAL_HEALTH = "http://127.0.0.1:8000/health"
TUNNEL_URL = "https://chibio.primbiolab.org"
CAMERA_TUNNEL_HEALTH = "https://camera.primbiolab.org/health"

# Valores por defecto (validados manualmente en esta PC). El panel los
# corrige en tiempo real si detecta adaptadores distintos antes de
# correr compartir_red_beaglebone.ps1 — ver _detect_network_adapters().
DEFAULT_WIFI_INDEX = 4
DEFAULT_USB_INDEX = 39
USB_EXPECTED_IP = "192.168.7.1"

WIFI_PATTERN = re.compile(r"wireless|wi-?fi|802\.11|wlan", re.I)
USB_PATTERN = re.compile(r"remote ndis|rndis|usb ethernet|linux usb|cdc ether", re.I)

OK = "OK"
FALLA = "FALLA"
DESCONOCIDO = "?"

# Paleta tomada de static/css/nexus.css (tema oscuro) para que el panel del
# PC se vea como una extension del propio Nexus, no como una app generica.
COLOR = {
    "bg": "#0b0e14", "s1": "#10141c", "s2": "#181e2a", "s3": "#1e2638",
    "bd": "#253045", "bd2": "#2e3a52",
    "gr": "#00d68f", "gr_d": "#0f2e26",
    "bl": "#4a9eff", "bl_d": "#142a40",
    "tx": "#e2ecf8", "tx2": "#a0bcd4", "tx3": "#6080a0",
    "err": "#ff5c6c", "err_d": "#33181c",
}
F_UI = "Segoe UI"
F_MONO = "Consolas"

ctk.set_appearance_mode("dark")


def _resource_path(*parts):
    """Resuelve rutas a scripts/* tanto en modo .py como empacado en .exe.

    Los .ps1 viajan EMBEBIDOS en el .exe (--add-data) y PyInstaller los
    extrae a una carpeta temporal (sys._MEIPASS) en cada arranque — sirve
    para ejecutarlos, pero esa carpeta NO es el repo real.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _project_root():
    """Carpeta de trabajo persistente: donde el .exe vive (o donde esta este .py en dev).

    En modo .exe: carpeta del ejecutable. requirements-windows.txt viene embebido
    en el .exe (sys._MEIPASS) y se extrae aqui la primera vez que se llama
    "Instalar todo", por lo que el exe puede colocarse en cualquier carpeta.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _tcp_check(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_check(url, timeout=3):
    # Cloudflare WAF bloquea el User-Agent default de urllib (Python-urllib/x.y)
    # con 403, aunque el sitio responda 200 normal a cualquier navegador/curl.
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except Exception:
        return False


def _usb_ip_check(usb_index):
    """Consulta (sin elevar) si el adaptador USB de la BBB ya tiene la IP esperada."""
    try:
        cmd = (
            f"(Get-NetIPAddress -InterfaceIndex {usb_index} "
            f"-AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.stdout.strip() == USB_EXPECTED_IP
    except Exception:
        return False


def _detect_network_adapters():
    """Enumera adaptadores de red (sin elevar) y separa candidatos WiFi / USB-BBB.

    Devuelve (wifi_candidates, usb_candidates), cada uno lista de dicts
    {Name, ifIndex, InterfaceDescription, Status}. Prefiere adaptadores
    con Status == 'Up' cuando hay varios que matchean el mismo patron.
    """
    cmd = (
        "@(Get-NetAdapter | Select-Object Name, ifIndex, InterfaceDescription, Status) "
        "| ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        adapters = json.loads(out.stdout.strip() or "[]")
    except Exception:
        return [], []

    if isinstance(adapters, dict):
        adapters = [adapters]

    wifi = [a for a in adapters if WIFI_PATTERN.search(a.get("InterfaceDescription", ""))]
    usb = [a for a in adapters if USB_PATTERN.search(a.get("InterfaceDescription", ""))]

    def _prefer_up(candidates):
        up = [a for a in candidates if a.get("Status") == "Up"]
        return up if up else candidates

    return _prefer_up(wifi), _prefer_up(usb)


def _ping_check(host, timeout_ms=1000):
    """Ping simple (sin elevar) para distinguir 'host inalcanzable' de 'puerto cerrado'."""
    try:
        out = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), host],
            capture_output=True, text=True, timeout=timeout_ms / 1000 + 2,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.returncode == 0
    except Exception:
        return False


def _service_status(name):
    """Estado de un servicio NSSM via Get-Service. 'NoExiste' si no esta instalado."""
    try:
        cmd = f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status"
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        status = out.stdout.strip()
        return status if status else "NoExiste"
    except Exception:
        return "Desconocido"


def _buscar_cloudflared():
    """Busca cloudflared.exe en todo el sistema, no en una sola ruta hardcodeada.

    Los 2 scripts del repo usan defaults DISTINTOS (instalar_todo.ps1 ->
    Documents\\cloudflared, instalar_servicios.ps1 -> Program Files (x86)\\cloudflared)
    y el usuario puede tenerlo en cualquier otro lado via winget/manual. La fuente
    mas confiable es preguntarle a Windows: PATH (Get-Command) + ubicaciones
    tipicas que usan los .ps1 de este repo. Nota: NSSM registra su PROPIO
    nssm.exe como binario del servicio (no el exe envuelto), asi que leer
    Win32_Service.PathName de ChibioTunnel daria nssm.exe, no cloudflared.exe
    — descartado a proposito, es un falso candidato. Devuelve la ruta o "".
    """
    cmd = (
        "$c = @("
        "(Join-Path $env:USERPROFILE 'Documents\\cloudflared\\cloudflared.exe'),"
        "'C:\\Program Files (x86)\\cloudflared\\cloudflared.exe',"
        "'C:\\Program Files\\cloudflared\\cloudflared.exe'"
        ");"
        "$g = Get-Command cloudflared -ErrorAction SilentlyContinue;"
        "if ($g) { $c += $g.Source }"
        "($c | Where-Object { Test-Path $_ } | Select-Object -First 1)"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _log_dir_servicio(nombre, proyecto):
    """Carpeta donde instalar_servicios.ps1 configuro AppStdout/AppStderr para cada servicio."""
    if nombre == "ChibioTunnel":
        return os.path.join(os.path.expanduser("~"), ".cloudflared")
    return proyecto


def _leer_log(path, max_lineas=120):
    """Ultimas N lineas de un log NSSM (AppStdout/AppStderr). No falla si no existe aun."""
    if not os.path.isfile(path):
        return f"(no existe todavia: {path})"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lineas = f.readlines()
        contenido = "".join(lineas[-max_lineas:])
        return contenido if contenido.strip() else "(vacio)"
    except Exception as e:
        return f"(error leyendo log: {e})"


def _adapter_exists(if_index):
    """Confirma (sin elevar) que un InterfaceIndex todavia corresponde a un adaptador real."""
    try:
        cmd = f"(Get-NetAdapter -InterfaceIndex {if_index} -ErrorAction SilentlyContinue).ifIndex"
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.stdout.strip() == str(if_index)
    except Exception:
        return False


def _run_ps1_elevated(script_name, wait=True, extra_args=None):
    """Lanza un .ps1 con UAC (Start-Process -Verb RunAs). El panel mismo no requiere admin."""
    script_path = _resource_path("scripts", "pc", script_name)
    args_str = f' -File "{script_path}"'
    if extra_args:
        args_str += " " + " ".join(extra_args)
    ps_cmd = (
        f"Start-Process -FilePath powershell.exe "
        f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass{args_str}' "
        f"-Verb RunAs"
    )
    if wait:
        ps_cmd += " -Wait"
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f"{script_name} falló (powershell.exe exitó con {result.returncode})")


def _font(family=F_UI, size=13, weight="normal"):
    return ctk.CTkFont(family=family, size=size, weight=weight)


def _card(parent, fg_color=None, border_color=None, **kwargs):
    """Card con esquinas redondeadas + borde — CTkFrame lo soporta nativo,
    a diferencia de tk.Frame que necesitaba el truco de doble-frame anidado."""
    return ctk.CTkFrame(
        parent,
        corner_radius=16,
        fg_color=fg_color or COLOR["s1"],
        border_width=1,
        border_color=border_color or COLOR["bd"],
        **kwargs,
    )


def _card_title(parent, icon, texto, icon_size=20, title_size=14, color=None, **pack_kwargs):
    """Encabezado de card: icono y texto en Labels SEPARADOS, no concatenados
    en un solo string. Los emoji de Segoe UI Emoji rasterizan borrosos/pixelados
    cuando comparten Label con texto a tamaño de fuente chico — separarlos deja
    poner el icono grande (nitido) sin forzar el texto del titulo al mismo tamaño."""
    color = color or COLOR["tx3"]
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(anchor="w", fill="x", **pack_kwargs)
    ctk.CTkLabel(row, text=icon, font=_font(size=icon_size), text_color=color).pack(
        side="left", padx=(0, 8)
    )
    ctk.CTkLabel(row, text=texto, font=_font(F_UI, title_size, "bold"),
                 text_color=color).pack(side="left")
    return row


class _Tooltip:
    """Tooltip simple que aparece al hacer hover sobre un widget."""

    def __init__(self, widget, text):
        self._w = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e):
        x = self._w.winfo_rootx() + 10
        y = self._w.winfo_rooty() + self._w.winfo_height() + 6
        self._tip = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self._text, justify="left",
            background=COLOR["s2"], foreground=COLOR["tx2"],
            relief="flat", bd=1, font=(F_UI, 10),
            padx=10, pady=6, wraplength=300,
        ).pack()

    def _hide(self, _e):
        if self._tip:
            self._tip.destroy()
            self._tip = None


NAV_ITEMS = (
    ("inicio", "🏠", "Inicio"),
    ("red", "📶", "Red"),
    ("indices", "📊", "Índices"),
    ("camara", "📷", "Cámara"),
    ("ajustes", "⚙", "Ajustes"),
)

TOUR_STEPS = [
    {
        "pagina": "inicio",
        "titulo": "Bienvenido al Panel de Control",
        "texto": (
            "Este panel te permite verificar y controlar todos los componentes "
            "del sistema Chi.Bio desde tu PC: la BeagleBone, la cámara y el "
            "túnel de acceso remoto."
        ),
    },
    {
        "pagina": "inicio",
        "titulo": "Estado del sistema",
        "texto": (
            "Aquí ves en tiempo real el estado de las 4 conexiones que "
            "Chi.Bio necesita para funcionar.\n\n"
            "Verde = OK · Rojo = hay algo que resolver."
        ),
    },
    {
        "pagina": "inicio",
        "titulo": "Diagnóstico completo",
        "texto": (
            "Si algo aparece en rojo, usa este botón. Analiza cada conexión "
            "individualmente y te indica exactamente qué falló y cómo resolverlo."
        ),
    },
    {
        "pagina": "red",
        "titulo": "Servidores del PC",
        "texto": (
            "Aquí ves el estado de los dos servidores que corren en este PC: "
            "el servidor de cámara y el túnel Cloudflare.\n\n"
            "Puedes ver sus registros o reiniciarlos individualmente."
        ),
    },
    {
        "pagina": "red",
        "titulo": "Control de servicios",
        "texto": (
            "Inicia o detiene ambos servidores a la vez con un solo clic.\n\n"
            "Usa 'Instalar dependencias y servicios' la primera vez que "
            "configures el sistema en un PC nuevo."
        ),
    },
    {
        "pagina": "indices",
        "titulo": "Índices de red",
        "texto": (
            "Windows asigna un número a cada adaptador de red. Aquí identificas "
            "cuál corresponde a tu WiFi y cuál a la BeagleBone.\n\n"
            "Sigue los 3 pasos en orden: Comprobar → Configurar → Compartir."
        ),
    },
    {
        "pagina": "camara",
        "titulo": "Vista previa de cámara",
        "texto": (
            "Aquí puedes verificar que el servidor de cámara esté funcionando "
            "y ver el feed en vivo directamente desde el panel."
        ),
    },
    {
        "pagina": "ajustes",
        "titulo": "Ajustes del túnel",
        "texto": (
            "Si necesitas acceder a Chi.Bio desde fuera de tu red local, "
            "aquí configuras tu túnel Cloudflare con tu propio dominio.\n\n"
            "Solo necesitas hacerlo una vez por instalación."
        ),
    },
]


class PanelControl(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Chi.Bio Nexus — Panel de Control")
        self.geometry("960x760")
        self.minsize(860, 600)
        self.configure(fg_color=COLOR["bg"])
        self.resizable(True, True)
        self._logo_img = None
        self._dialog_icon_ref = None
        self._negro_ico_path = None
        self._blanco_ico_path = None
        try:
            _logo_pil = Image.open(_resource_path("assets", "logo.png"))
            self._logo_img = ctk.CTkImage(
                light_image=_logo_pil, dark_image=_logo_pil, size=(40, 40)
            )
            _ico_blanco = _resource_path("assets", "logo_blanco.ico")
            _logo_pil.save(_ico_blanco, format="ICO", sizes=[(16, 16), (32, 32), (64, 64)])
            self._blanco_ico_path = _ico_blanco
            self.after(0, lambda: self.iconbitmap(_ico_blanco))
        except Exception:
            try:
                self.iconbitmap(_resource_path("assets", "nexus.ico"))
            except Exception:
                pass
        try:
            _negro_pil = Image.open(_resource_path("assets", "logo_negro.png"))
            _ico_negro = _resource_path("assets", "logo_negro.ico")
            _negro_pil.save(_ico_negro, format="ICO", sizes=[(16, 16), (32, 32), (64, 64)])
            self._dialog_icon_ref = ImageTk.PhotoImage(_negro_pil.resize((64, 64), Image.LANCZOS))
            self._negro_ico_path = _ico_negro
        except Exception:
            pass

        self.rows = {}
        self.paginas = {}
        self.nav_botones = {}
        self.wifi_index = DEFAULT_WIFI_INDEX
        self.usb_index = DEFAULT_USB_INDEX
        self._use_tunnel = True  # sobreescrito por JSON o wizard
        self._indices_lock = threading.Lock()
        self._prev_estado = {}
        self._cargar_config_urls()
        self._cargar_estado_local()
        if self._use_tunnel is None:
            self._wizard_tunel()
        self._build_ui()
        self._mostrar_pagina("inicio")
        self._verificar_estado()
        self._iniciar_autodeteccion_bbb()
        self._iniciar_auto_refresh()
        self.after(1500, self._chequear_gemini_key)

    def destroy(self):
        self._autodeteccion_activa = False
        self._auto_refresh_activo = False
        super().destroy()

    # ------------------------------------------------------------------
    # UI: topbar + rail de navegacion + paginas + footer de estado
    # ------------------------------------------------------------------
    def _build_ui(self):
        topbar = ctk.CTkFrame(self, fg_color=COLOR["s1"], corner_radius=0, height=64)
        topbar.pack(fill="x", side="top")
        ctk.CTkFrame(self, fg_color=COLOR["bd"], corner_radius=0, height=1).pack(fill="x")

        if self._logo_img:
            ctk.CTkLabel(
                topbar, text="", image=self._logo_img,
                fg_color="transparent", width=46, height=46,
            ).pack(side="left", padx=(20, 12), pady=9)
        else:
            ctk.CTkLabel(
                topbar, text="⚙", font=_font(size=20), fg_color="transparent",
                text_color=COLOR["gr"], width=46, height=46,
            ).pack(side="left", padx=(20, 12), pady=9)

        title_box = ctk.CTkFrame(topbar, fg_color="transparent")
        title_box.pack(side="left", pady=10)
        title_row = ctk.CTkFrame(title_box, fg_color="transparent")
        title_row.pack(anchor="w")
        ctk.CTkLabel(title_row, text="Chi.Bio", font=_font(size=18, weight="bold"),
                     text_color=COLOR["tx"]).pack(side="left")
        ctk.CTkLabel(title_row, text=" Nexus", font=_font(size=18, weight="bold"),
                     text_color=COLOR["gr"]).pack(side="left")
        ctk.CTkLabel(title_box, text="PANEL DE CONTROL — PC", font=_font(F_UI, 10),
                     text_color=COLOR["tx3"]).pack(anchor="w")

        btn_tour = self._make_button(
            topbar, "Tour guiado", self._iniciar_tour, width=110, height=34,
        )
        btn_tour.pack(side="right", padx=(0, 18), pady=15)
        _Tooltip(btn_tour, "Recorre el panel paso a paso con explicaciones de cada sección.")

        btn_abrir = self._make_button(
            topbar, "Abrir Nexus", self._abrir_navegador, variant="primary", width=120, height=34,
        )
        btn_abrir.pack(side="right", padx=(0, 6), pady=15)
        _Tooltip(btn_abrir, "Abre Chi.Bio Nexus en el navegador. Prioriza el túnel si está disponible, o LAN si no.")

        content = ctk.CTkFrame(self, fg_color=COLOR["bg"], corner_radius=0)
        content.pack(fill="both", expand=True)

        nav_rail = ctk.CTkFrame(content, fg_color=COLOR["s1"], corner_radius=0, width=152)
        nav_rail.pack(side="left", fill="y")
        nav_rail.pack_propagate(False)

        main_area = ctk.CTkFrame(content, fg_color=COLOR["bg"], corner_radius=0)
        main_area.pack(side="left", fill="both", expand=True)

        self._build_nav(nav_rail)
        self._build_paginas(main_area)

        self.footer = ctk.CTkFrame(self, fg_color=COLOR["s1"], corner_radius=0, height=30)
        self.footer.pack(fill="x", side="bottom")
        self.log_var = tk.StringVar(value="Listo.")
        self.log_label = ctk.CTkLabel(
            self.footer, textvariable=self.log_var, font=_font(F_MONO, 9),
            text_color=COLOR["tx3"],
        )
        self.log_label.pack(side="left", padx=16, pady=4)

    def _build_nav(self, rail):
        for key, icon, etiqueta in NAV_ITEMS:
            # Frame clickeable con 2 Labels SEPARADOS (icono grande / texto chico)
            # en vez de un CTkButton con texto multilinea "icono\ntexto": un emoji
            # de Segoe UI Emoji metido en el mismo Label que texto a 10-11pt
            # rasteriza borroso — separarlo permite un icono grande y nitido.
            item = ctk.CTkFrame(rail, corner_radius=12, fg_color="transparent",
                                 width=128, height=72)
            item.pack(padx=13, pady=(14 if key == "inicio" else 7, 7))
            item.pack_propagate(False)

            icon_lbl = ctk.CTkLabel(item, text=icon, font=_font(size=26),
                                     text_color=COLOR["tx2"])
            icon_lbl.pack(pady=(10, 0))
            text_lbl = ctk.CTkLabel(item, text=etiqueta, font=_font(size=11, weight="bold"),
                                     text_color=COLOR["tx2"])
            text_lbl.pack(pady=(2, 8))

            for widget in (item, icon_lbl, text_lbl):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, k=key: self._mostrar_pagina(k))

            self.nav_botones[key] = (item, icon_lbl, text_lbl)

        # Indicador BBB siempre visible en el pie del rail, sin importar la
        # pagina activa — auto-detectado en hilo de fondo (ver mas abajo).
        bbb_box = _card(rail, fg_color=COLOR["s2"])
        bbb_box.pack(side="bottom", fill="x", padx=12, pady=16)
        self.bbb_canvas = tk.Canvas(
            bbb_box, width=26, height=26, bg=COLOR["s2"], highlightthickness=0,
        )
        self.bbb_canvas.pack(pady=(14, 6))
        self.bbb_text_var = tk.StringVar(value="Detectando...")
        ctk.CTkLabel(
            bbb_box, textvariable=self.bbb_text_var, font=_font(F_MONO, 10),
            text_color=COLOR["tx3"], wraplength=100, justify="center",
        ).pack(pady=(0, 14), padx=6)
        self._dibujar_dot_bbb(None)

    def _mostrar_pagina(self, key):
        for k, frame in self.paginas.items():
            frame.pack_forget()
        self.paginas[key].pack(fill="both", expand=True)
        for k, (item, icon_lbl, text_lbl) in self.nav_botones.items():
            if k == key:
                item.configure(fg_color=COLOR["gr_d"])
                icon_lbl.configure(text_color=COLOR["gr"])
                text_lbl.configure(text_color=COLOR["gr"])
            else:
                item.configure(fg_color="transparent")
                icon_lbl.configure(text_color=COLOR["tx2"])
                text_lbl.configure(text_color=COLOR["tx2"])

    def _crear_pagina(self, parent, key):
        frame = ctk.CTkScrollableFrame(parent, fg_color=COLOR["bg"], corner_radius=0)
        self.paginas[key] = frame
        return frame

    def _build_paginas(self, main_area):
        self._build_pagina_inicio(self._crear_pagina(main_area, "inicio"))
        self._build_pagina_red(self._crear_pagina(main_area, "red"))
        self._build_pagina_indices(self._crear_pagina(main_area, "indices"))
        self._build_pagina_camara(self._crear_pagina(main_area, "camara"))
        self._build_pagina_ajustes(self._crear_pagina(main_area, "ajustes"))

    # ------------------------------------------------------------------
    # Pagina: Inicio — diagnostico del sistema (lo primero que se ve)
    # ------------------------------------------------------------------
    def _build_pagina_inicio(self, page):
        status_card = _card(page)
        status_card.pack(fill="x", padx=22, pady=(20, 14))
        _card_title(status_card, "🖥", "ESTADO DEL SISTEMA", padx=18, pady=(16, 8))

        rows_frame = ctk.CTkFrame(status_card, fg_color="transparent")
        rows_frame.pack(fill="x", padx=14, pady=(0, 16))

        self._add_status_row(rows_frame, "red", "1. Red compartida PC → BBB")
        self._add_status_row(rows_frame, "bbb", "2. Servidor BBB")
        self._add_status_row(rows_frame, "camara", "3. Cámara local")
        if self._use_tunnel:
            self._add_status_row(rows_frame, "tunel", "4. Túnel Cloudflare")

        btn_diag = self._make_button(
            page, "Diagnóstico completo",
            self._accion_diagnostico, variant="primary", width=480, height=46,
        )
        btn_diag.pack(padx=22, pady=(0, 10))
        _Tooltip(btn_diag, "Analiza cada conexión en detalle e indica exactamente qué falló y cómo resolverlo.")

        btn_rep = self._make_button(
            page, "Generar reporte .txt", self._accion_generar_reporte,
            width=480, height=42,
        )
        btn_rep.pack(padx=22, pady=(0, 16))
        _Tooltip(btn_rep, "Genera un archivo de texto con el diagnóstico completo para compartir con soporte técnico.")


    # ------------------------------------------------------------------
    # Pagina: Red — servidores NSSM (camara/tunel) + abrir navegador
    # ------------------------------------------------------------------
    def _build_pagina_red(self, page):
        srv_card = _card(page)
        srv_card.pack(fill="x", padx=22, pady=(0, 22))
        _card_title(srv_card, "📡", "SERVIDORES (NSSM)", padx=18, pady=(16, 8))

        self.srv_labels = {}
        servicios = [("ChibioCamera", "Servidor de cámara")]
        if self._use_tunnel:
            servicios.append(("ChibioTunnel", "Túnel Cloudflare"))
        for nombre, etiqueta in servicios:
            row = ctk.CTkFrame(srv_card, fg_color=COLOR["s2"], corner_radius=12)
            row.pack(fill="x", padx=14, pady=6)

            ctk.CTkLabel(row, text=etiqueta, anchor="w", font=_font(size=13),
                         text_color=COLOR["tx2"]).pack(
                side="left", padx=(14, 8), pady=12, fill="x", expand=True
            )

            estado_lbl = ctk.CTkLabel(
                row, text=DESCONOCIDO, font=_font(F_MONO, 10, "bold"),
                text_color=COLOR["tx3"], fg_color=COLOR["s3"], corner_radius=9,
                width=90, height=28,
            )
            estado_lbl.pack(side="left", padx=(0, 10), pady=10)
            self.srv_labels[nombre] = estado_lbl

            self._make_button(
                row, "Logs", lambda n=nombre: self._accion_ver_logs(n), width=92,
            ).pack(side="left", padx=3, pady=8)
            self._make_button(
                row, "Reiniciar", lambda n=nombre: self._accion_reiniciar_servicio(n),
                width=116,
            ).pack(side="left", padx=(3, 14), pady=8)

        ctk.CTkFrame(srv_card, fg_color="transparent", height=8).pack()

        act_card = _card(page)
        act_card.pack(fill="x", padx=22, pady=(0, 16))
        _card_title(act_card, "⚡", "CONTROL DE SERVICIOS", padx=18, pady=(16, 10))

        btn_grid = ctk.CTkFrame(act_card, fg_color="transparent")
        btn_grid.pack(padx=14, pady=(0, 20))

        btn_ini = self._make_button(btn_grid, "Iniciar servicios", self._accion_iniciar_servicios, width=190)
        btn_ini.grid(row=0, column=0, padx=6, pady=6)
        _Tooltip(btn_ini, "Inicia el servidor de cámara" + (" y el túnel Cloudflare." if self._use_tunnel else "."))

        btn_det = self._make_button(btn_grid, "Detener servicios", self._accion_detener_servicios, width=190, variant="danger")
        btn_det.grid(row=0, column=1, padx=6, pady=6)
        _Tooltip(btn_det, "Detiene el servidor de cámara" + (" y el túnel Cloudflare." if self._use_tunnel else "."))

        btn_ver = self._make_button(btn_grid, "Verificar estado", self._verificar_estado, width=190)
        btn_ver.grid(row=0, column=2, padx=6, pady=6)
        _Tooltip(btn_ver, "Actualiza el estado de todas las conexiones en la pestaña Inicio.")

        btn_inst = self._make_button(
            page, "Instalar dependencias y servicios", self._accion_instalar_todo,
            variant="primary", width=480, height=46,
        )
        btn_inst.pack(padx=22, pady=(0, 20))
        _Tooltip(btn_inst, "Primera vez: instala Python, NSSM, cloudflared y configura los servicios de Windows.")

    # ------------------------------------------------------------------
    # Pagina: Indices de red (WiFi / BBB)
    # ------------------------------------------------------------------
    def _build_pagina_indices(self, page):
        idx_card = _card(page)
        idx_card.pack(fill="x", padx=22, pady=(20, 22))
        _card_title(idx_card, "📶", "ÍNDICES DE RED (WiFi / BBB)", padx=18, pady=(16, 8))

        ctk.CTkLabel(
            idx_card,
            text="Windows asigna un número de índice a cada adaptador de red.\n"
                 "Este panel necesita identificar cuál es tu adaptador WiFi y cuál\n"
                 "corresponde a la BeagleBone conectada por USB, para poder\n"
                 "compartir la conexión a internet correctamente.",
            font=_font(F_UI, 12), text_color=COLOR["tx2"],
            justify="left", anchor="w", wraplength=520,
        ).pack(fill="x", padx=18, pady=(0, 14))

        indices_row = ctk.CTkFrame(idx_card, fg_color="transparent")
        indices_row.pack(anchor="w", padx=14, pady=(0, 16))

        wifi_card = ctk.CTkFrame(indices_row, fg_color=COLOR["gr_d"], corner_radius=12,
                                  border_width=1, border_color=COLOR["gr"])
        wifi_card.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(wifi_card, text="WiFi", font=_font(F_UI, 10),
                     text_color=COLOR["gr"]).pack(padx=20, pady=(10, 2))
        self.wifi_idx_label = ctk.CTkLabel(wifi_card, text=str(self.wifi_index),
                                            font=_font(F_MONO, 24, "bold"), text_color=COLOR["gr"])
        self.wifi_idx_label.pack(padx=20, pady=(0, 10))

        usb_card = ctk.CTkFrame(indices_row, fg_color=COLOR["gr_d"], corner_radius=12,
                                 border_width=1, border_color=COLOR["gr"])
        usb_card.pack(side="left")
        ctk.CTkLabel(usb_card, text="BBB (USB)", font=_font(F_UI, 10),
                     text_color=COLOR["gr"]).pack(padx=20, pady=(10, 2))
        self.usb_idx_label = ctk.CTkLabel(usb_card, text=str(self.usb_index),
                                           font=_font(F_MONO, 24, "bold"), text_color=COLOR["gr"])
        self.usb_idx_label.pack(padx=20, pady=(0, 10))

        idx_btn_grid = ctk.CTkFrame(idx_card, fg_color="transparent")
        idx_btn_grid.pack(padx=14, pady=(0, 20))

        btn_comp = self._make_button(idx_btn_grid, "1. Comprobar índices", self._accion_comprobar_indices, width=190)
        btn_comp.grid(row=0, column=0, padx=6, pady=6)
        _Tooltip(btn_comp, "Detecta y muestra los adaptadores WiFi y USB disponibles en este PC. No cambia nada.")

        btn_conf = self._make_button(idx_btn_grid, "2. Configurar índices", self._accion_configurar_indices, width=190)
        btn_conf.grid(row=0, column=1, padx=6, pady=6)
        _Tooltip(btn_conf, "Aplica automáticamente los índices correctos. Si hay ambigüedad, abre un diálogo para elegir.")

        btn_comp_red = self._make_button(idx_btn_grid, "3. Compartir red", self._accion_compartir_red, width=190)
        btn_comp_red.grid(row=0, column=2, padx=6, pady=6)
        _Tooltip(btn_comp_red, "Comparte la conexión WiFi a la BeagleBone por USB. Requiere permiso de administrador.")

        self._refresh_indices_label()

    # ------------------------------------------------------------------
    # Pagina: Camara — abre visor WebRTC offline en el navegador
    # ------------------------------------------------------------------
    def _build_pagina_camara(self, page):
        cam_card = _card(page)
        cam_card.pack(fill="x", padx=22, pady=(20, 14))
        _card_title(cam_card, "📷", "CÁMARA", padx=18, pady=(16, 8))

        ctk.CTkLabel(
            cam_card,
            text="El servidor de cámara corre en este PC de forma independiente.\n"
                 "El visor WebRTC funciona sin internet ni conexión a la BeagleBone.",
            font=_font(F_UI, 12), text_color=COLOR["tx2"],
            justify="left", anchor="w", wraplength=520,
        ).pack(fill="x", padx=18, pady=(0, 14))

        btn = self._make_button(
            cam_card, "Ver cámara en el navegador",
            self._abrir_camara_navegador, variant="primary", width=280, height=46,
        )
        btn.pack(padx=18, pady=(0, 22))
        _Tooltip(btn, "Abre un visor WebRTC offline en el navegador. No requiere BBB ni internet.")

    # ------------------------------------------------------------------
    # Pagina: Ajustes — reconfigurar el tunel Cloudflare a mano
    # ------------------------------------------------------------------
    def _build_pagina_ajustes(self, page):
        card = _card(page)
        card.pack(fill="x", padx=22, pady=(20, 22))
        _card_title(card, "⚙", "AJUSTES", padx=18, pady=(16, 10))

        if self._use_tunnel:
            ctk.CTkLabel(
                card,
                text="Aquí se configura el servidor Cloudflare Tunnel, que permite acceder\n"
                     "a Chi.Bio Nexus desde internet con tu propio dominio.\n\n"
                     "Al presionar el botón, podrás ingresar los siguientes parámetros:\n"
                     "  · Nombre del túnel (creado en tu cuenta de Cloudflare)\n"
                     "  · Dominio principal del Nexus\n"
                     "  · Dominio de la cámara\n\n"
                     "La configuración se guarda localmente en este PC.",
                font=_font(size=12), text_color=COLOR["tx2"], justify="left", anchor="w",
                wraplength=560,
            ).pack(fill="x", padx=18, pady=(0, 16))
            btn_tun = self._make_button(
                card, "Configurar túnel Cloudflare",
                lambda: self._abrir_dialogo_tunel(_project_root()), width=260,
            )
            btn_tun.pack(anchor="w", padx=18, pady=(0, 10))
            _Tooltip(btn_tun, "Guarda el nombre del túnel y los dominios en este PC sin tener que reinstalar todo.")
            btn_des = self._make_button(
                card, "Desactivar túnel (solo LAN)", self._cambiar_preferencia_tunel,
                width=260,
            )
            btn_des.pack(anchor="w", padx=18, pady=(0, 18))
            _Tooltip(btn_des, "Cambia el panel a modo solo red local. Se aplica al reiniciar el panel.")
        else:
            ctk.CTkLabel(
                card,
                text="Panel configurado en modo solo red local.\n"
                     "Chi.Bio Nexus solo es accesible desde dentro de tu red.\n\n"
                     "Si necesitas acceso remoto por internet, activa el túnel\n"
                     "Cloudflare con el botón de abajo.",
                font=_font(size=12), text_color=COLOR["tx2"], justify="left", anchor="w",
                wraplength=560,
            ).pack(fill="x", padx=18, pady=(0, 16))
            btn_act = self._make_button(
                card, "Activar túnel Cloudflare", self._cambiar_preferencia_tunel,
                variant="primary", width=260,
            )
            btn_act.pack(anchor="w", padx=18, pady=(0, 18))
            _Tooltip(btn_act, "Activa el modo de acceso remoto. Se aplica al reiniciar el panel.")

    def _make_button(self, parent, text, command, variant=None, width=140, height=36):
        """variant: None (neutral), 'primary' (verde, accion destacada),
        'danger' (rojo, accion destructiva como detener servicios)."""
        if variant == "primary":
            fg, hover, text_color, border = COLOR["gr_d"], COLOR["gr"], COLOR["tx"], COLOR["gr"]
        elif variant == "danger":
            fg, hover, text_color, border = COLOR["err_d"], COLOR["err"], COLOR["tx"], COLOR["err"]
        else:
            fg, hover, text_color, border = COLOR["s2"], COLOR["bd2"], COLOR["tx2"], COLOR["bd"]

        btn = ctk.CTkButton(
            parent, text=text, command=command, width=width, height=height,
            corner_radius=11, fg_color=fg, hover_color=hover, text_color=text_color,
            border_width=1, border_color=border, font=_font(size=13, weight="bold"),
            cursor="hand2",
        )
        return btn

    def _icon_negro(self):
        if self._negro_ico_path:
            self.iconbitmap(self._negro_ico_path)

    def _icon_blanco(self):
        if self._blanco_ico_path:
            self.iconbitmap(self._blanco_ico_path)

    def _msg_info(self, title, msg):
        self._icon_negro()
        messagebox.showinfo(title, msg, parent=self)
        self._icon_blanco()

    def _msg_yesno(self, title, msg, **kw):
        self._icon_negro()
        result = messagebox.askyesno(title, msg, parent=self, **kw)
        self._icon_blanco()
        return result

    def _msg_warn(self, title, msg):
        self._icon_negro()
        messagebox.showwarning(title, msg, parent=self)
        self._icon_blanco()

    def _msg_error(self, title, msg):
        self._icon_negro()
        messagebox.showerror(title, msg, parent=self)
        self._icon_blanco()

    def _set_log(self, text):
        self.log_var.set(text)
        busy = text.endswith("...")
        self.footer.configure(fg_color=COLOR["gr_d"] if busy else COLOR["s1"])
        self.log_label.configure(text_color=COLOR["gr"] if busy else COLOR["tx3"])

    def _add_status_row(self, parent, key, label_text):
        row = ctk.CTkFrame(parent, fg_color=COLOR["s2"], corner_radius=12)
        row.pack(fill="x", pady=5)

        dot = tk.Canvas(row, width=18, height=18, bg=COLOR["s2"], highlightthickness=0)
        dot_id = dot.create_oval(3, 3, 15, 15, fill=COLOR["tx3"], outline="")
        dot.pack(side="left", padx=(16, 10), pady=12)

        ctk.CTkLabel(
            row, text=label_text, anchor="w", font=_font(size=13),
            text_color=COLOR["tx2"],
        ).pack(side="left", fill="x", expand=True, pady=12)

        value_label = ctk.CTkLabel(
            row, text=DESCONOCIDO, font=_font(F_MONO, 10, "bold"),
            text_color=COLOR["tx3"], fg_color=COLOR["s3"], corner_radius=9,
            width=86, height=28,
        )
        value_label.pack(side="right", padx=(0, 14), pady=10)

        self.rows[key] = (dot, dot_id, value_label)

    # ------------------------------------------------------------------
    # Indicador BBB: glow simulado (varios anillos concentricos) +
    # auto-deteccion en hilo de fondo, siempre visible en el rail.
    # ------------------------------------------------------------------
    @staticmethod
    def _mix_hex(c1, c2, t):
        """Interpola entre 2 colores hex (0..1) — usado para simular el glow."""
        c1, c2 = c1.lstrip("#"), c2.lstrip("#")
        r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
        r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _dibujar_dot_bbb(self, conectada):
        """Punto brillante: varios anillos concentricos degradando desde el
        fondo de la card hasta el color pleno — simula el glow/box-shadow
        que tk no soporta nativamente en un Canvas."""
        c = self.bbb_canvas
        c.delete("all")
        cx, cy = 13, 13
        bg = COLOR["s2"]
        if conectada is None:
            core = COLOR["tx3"]
        else:
            core = COLOR["gr"] if conectada else COLOR["err"]
        for radio, t in ((12, 0.25), (8, 0.55), (5, 1.0)):
            color = self._mix_hex(bg, core, t)
            c.create_oval(cx - radio, cy - radio, cx + radio, cy + radio,
                          fill=color, outline="")

    def _iniciar_autodeteccion_bbb(self):
        """Detecta cada 4s si hay un adaptador USB de la BBB presente —
        independiente de botones, siempre corriendo en hilo de fondo."""
        self._autodeteccion_activa = True

        def loop():
            while self._autodeteccion_activa:
                _, usb_candidates = _detect_network_adapters()
                # _detect_network_adapters() hace match por descripcion (RNDIS/USB
                # ethernet) y si ninguno esta 'Up' devuelve TODOS sin filtrar (asi
                # sirve para el dialogo manual). Aqui SI importa el estado real:
                # adaptador listado con cable desconectado queda en Disconnected/
                # Disabled/Not Present, no en Up.
                conectada = any(a.get("Status") == "Up" for a in usb_candidates)
                if self._autodeteccion_activa:
                    self.after(0, lambda c=conectada: self._actualizar_sidebar_bbb(c))
                time.sleep(4)

        threading.Thread(target=loop, daemon=True).start()

    def _actualizar_sidebar_bbb(self, conectada):
        self._dibujar_dot_bbb(conectada)
        self.bbb_text_var.set("USB detectado" if conectada else "USB desconectado")

    def _set_row(self, key, ok):
        dot, dot_id, label = self.rows[key]
        if ok:
            color = COLOR["gr"]
            dot.itemconfig(dot_id, fill=color)
            label.configure(text=OK, text_color=color, fg_color=COLOR["gr_d"])
        else:
            color = COLOR["err"]
            dot.itemconfig(dot_id, fill=color)
            label.configure(text=FALLA, text_color=color, fg_color=COLOR["err_d"])

    # ------------------------------------------------------------------
    # Verificacion (en hilo aparte para no congelar la UI)
    # ------------------------------------------------------------------
    def _verificar_estado(self):
        self._set_log("Verificando estado...")
        threading.Thread(target=self._verificar_estado_worker, daemon=True).start()

    def _verificar_estado_worker(self):
        with self._indices_lock:
            usb_idx = self.usb_index
        red_ok = _usb_ip_check(usb_idx)
        bbb_ok = _tcp_check(LOCAL_HOST, LOCAL_PORT)
        camara_ok = _http_check(CAMERA_LOCAL_HEALTH)
        tunel_ok = _http_check(self.tunnel_url) if self._use_tunnel else None
        cam_estado = _service_status("ChibioCamera")
        tun_estado = _service_status("ChibioTunnel") if self._use_tunnel else None

        def aplicar():
            self._set_row("red", red_ok)
            self._set_row("bbb", bbb_ok)
            self._set_row("camara", camara_ok)
            if self._use_tunnel:
                self._set_row("tunel", tunel_ok)
                self._set_servicio_label("ChibioTunnel", tun_estado, bbb_ok=bbb_ok)
            self._set_servicio_label("ChibioCamera", cam_estado)

            nuevo = {"red": red_ok, "bbb": bbb_ok, "camara": camara_ok}
            if self._use_tunnel:
                nuevo["tunel"] = tunel_ok
            nombres = {
                "red": "Red compartida", "bbb": "Servidor BBB",
                "camara": "Cámara", "tunel": "Túnel",
            }
            caidas = [
                nombres[k] for k, v in nuevo.items()
                if v is False and self._prev_estado.get(k) is True
            ]
            if caidas:
                self._set_log(f"⚠ Fallo detectado: {', '.join(caidas)}")
            elif self._use_tunnel and not bbb_ok and tun_estado == "Running":
                self._set_log("⚠ Túnel activo sin BBB → error 1033. Ve a Red → Detener servicios.")
            else:
                self._set_log("Estado actualizado.")
            self._prev_estado = nuevo

        self.after(0, aplicar)

    def _set_servicio_label(self, nombre, estado, bbb_ok=True):
        label = self.srv_labels.get(nombre)
        if not label:
            return
        if nombre == "ChibioTunnel" and estado == "Running" and not bbb_ok:
            label.configure(text="SIN ORIGEN", text_color="#ffb300", fg_color="#2a1e00")
            return
        if estado == "Running":
            color, fondo = COLOR["gr"], COLOR["gr_d"]
        elif estado in ("Stopped", "NoExiste"):
            color, fondo = COLOR["err"], COLOR["err_d"]
        else:
            color, fondo = COLOR["tx3"], COLOR["s3"]
        label.configure(text=estado, text_color=color, fg_color=fondo)

    # ------------------------------------------------------------------
    # Servidores NSSM: ver logs (AppStdout/AppStderr) y reiniciar individual
    # ------------------------------------------------------------------
    def _contenido_logs_servicio(self, nombre):
        proyecto = _project_root()
        directorio = _log_dir_servicio(nombre, proyecto)
        out_path = os.path.join(directorio, f"{nombre}.out.log")
        err_path = os.path.join(directorio, f"{nombre}.err.log")
        return (
            f"=== {nombre}.out.log ===\n{_leer_log(out_path)}\n\n"
            f"=== {nombre}.err.log ===\n{_leer_log(err_path)}"
        )

    def _accion_ver_logs(self, nombre):
        self._mostrar_dialogo_logs(nombre, self._contenido_logs_servicio(nombre))

    def _set_dialog_icon(self, dlg):
        if self._negro_ico_path:
            dlg.after(100, lambda: dlg.iconbitmap(self._negro_ico_path))
        elif self._dialog_icon_ref:
            dlg.after(100, lambda: dlg.iconphoto(True, self._dialog_icon_ref))

    def _mostrar_dialogo_logs(self, nombre, contenido):
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Logs — {nombre}")
        dlg.configure(fg_color=COLOR["s1"])
        self._set_dialog_icon(dlg)
        dlg.geometry("700x500")
        dlg.transient(self)

        text = ctk.CTkTextbox(
            dlg, font=_font(F_MONO, 10), fg_color=COLOR["s2"], text_color=COLOR["tx2"],
            corner_radius=12, wrap="none",
        )
        text.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        text.insert("1.0", contenido)
        text.configure(state="disabled")

        def actualizar():
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", self._contenido_logs_servicio(nombre))
            text.configure(state="disabled")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(pady=(0, 14))
        self._make_button(btns, "Actualizar", actualizar, width=120).pack(side="left", padx=5)
        self._make_button(btns, "Cerrar", dlg.destroy, width=120).pack(side="left", padx=5)

    def _accion_reiniciar_servicio(self, nombre):
        confirmado = self._msg_yesno(
            "Reiniciar servicio",
            f"¿Reiniciar {nombre}?\n\n"
            f"El servicio se detendrá por un momento y luego volverá a arrancar. "
            f"Windows pedirá confirmación de administrador.",
        )
        if not confirmado:
            return
        self._set_log(f"Reiniciando {nombre}...")
        self._run_async(
            lambda: _run_ps1_elevated(
                "reiniciar_servicio.ps1", extra_args=[f"-Servicio {nombre}"]
            ),
            f"{nombre} reiniciado. Verifica el estado.",
        )

    # ------------------------------------------------------------------
    # Diagnostico completo: igual que _verificar_estado pero con CAUSA
    # especifica por cada eslabon caido (no solo OK/FALLA).
    # ------------------------------------------------------------------
    def _accion_diagnostico(self):
        self._set_log("Corriendo diagnóstico completo...")
        threading.Thread(target=self._diagnostico_worker, daemon=True).start()

    def _diagnostico_worker(self):
        resultado = self._calcular_diagnostico()
        reporte = "\n\n".join(resultado["lineas"])

        def mostrar():
            self._set_log("Diagnóstico completo listo.")
            self._set_row("red", resultado["red_ok"])
            self._set_row("bbb", resultado["bbb_ok"])
            self._set_row("camara", resultado["camara_ok"])
            self._set_row("tunel", resultado["tunel_ok"])
            self._msg_info("Diagnóstico completo", reporte)

        self.after(0, mostrar)

    def _calcular_diagnostico(self):
        """Corre los 4 checks con causa especifica. Reusado por el boton de
        diagnostico y por el generador de reporte .txt — una sola fuente de verdad."""
        lineas = []

        with self._indices_lock:
            usb_index = self.usb_index
        usb_existe = _adapter_exists(usb_index)
        if not usb_existe:
            red_ok = False
            lineas.append(
                f"1. Red compartida: FALLA — BBB no detectada por USB "
                f"(ifIndex={usb_index} no existe). Conecta el cable USB "
                f"y corre '1. Comprobar índices'."
            )
        else:
            red_ok = _usb_ip_check(usb_index)
            lineas.append(
                "1. Red compartida: OK" if red_ok else
                f"1. Red compartida: FALLA — adaptador USB presente pero sin "
                f"IP {USB_EXPECTED_IP}. Corre '3. Compartir red'."
            )

        bbb_ok = _tcp_check(LOCAL_HOST, LOCAL_PORT)
        if bbb_ok:
            lineas.append("2. Servidor BBB: OK")
        elif not _ping_check(LOCAL_HOST):
            lineas.append(
                f"2. Servidor BBB: FALLA — {LOCAL_HOST} no responde a ping. "
                f"Revisa que la red este compartida (eslabón 1) y la BBB encendida."
            )
        else:
            lineas.append(
                f"2. Servidor BBB: FALLA — {LOCAL_HOST} responde ping pero el "
                f"puerto {LOCAL_PORT} esta cerrado. Gunicorn/Flask no esta "
                f"corriendo en la BBB (revisa cb.sh por PuTTY)."
            )

        camara_ok = _http_check(CAMERA_LOCAL_HEALTH)
        if camara_ok:
            lineas.append("3. Cámara local: OK")
        else:
            estado = _service_status("ChibioCamera")
            if estado == "NoExiste":
                lineas.append(
                    "3. Cámara local: FALLA — servicio ChibioCamera no instalado. "
                    "Corre 'Instalar todo'."
                )
            elif estado != "Running":
                lineas.append(
                    f"3. Cámara local: FALLA — servicio instalado pero detenido "
                    f"(estado={estado}). Usa 'Iniciar servicios PC'."
                )
            else:
                lineas.append(
                    "3. Cámara local: FALLA — servicio corriendo pero /health no "
                    "responde. Puede haber crasheado; revisa logs de uvicorn."
                )

        tunel_ok = None
        if self._use_tunnel:
            tunel_ok = _http_check(self.tunnel_url)
            if tunel_ok:
                lineas.append("4. Túnel Cloudflare: OK")
            else:
                estado = _service_status("ChibioTunnel")
                if estado == "NoExiste":
                    lineas.append(
                        "4. Túnel Cloudflare: FALLA — servicio ChibioTunnel no "
                        "instalado. Corre 'Instalar todo' (eligiendo usar túnel)."
                    )
                elif estado != "Running":
                    lineas.append(
                        f"4. Túnel Cloudflare: FALLA — servicio detenido "
                        f"(estado={estado}). Usa 'Iniciar servicios PC'."
                    )
                elif not bbb_ok:
                    lineas.append(
                        "4. Túnel Cloudflare: FALLA — servicio corriendo, pero "
                        "apunta a la BBB que está caída (ver eslabón 2). El túnel "
                        "en sí puede estar bien."
                    )
                else:
                    lineas.append(
                        "4. Túnel Cloudflare: FALLA — servicio corriendo y BBB "
                        "responde en LAN, pero el dominio no resuelve/responde. "
                        "Revisa config.yml/DNS o el estado del túnel en Cloudflare."
                    )

        return {
            "lineas": lineas,
            "red_ok": red_ok,
            "bbb_ok": bbb_ok,
            "camara_ok": camara_ok,
            "tunel_ok": tunel_ok,
        }

    # ------------------------------------------------------------------
    # Reporte .txt — todo el diagnostico + estado en un solo archivo,
    # pensado para pegar en un chat de soporte cuando algo falla raro.
    # ------------------------------------------------------------------
    def _accion_generar_reporte(self):
        self._set_log("Generando reporte...")
        threading.Thread(target=self._generar_reporte_worker, daemon=True).start()

    def _generar_reporte_worker(self):
        proyecto = _project_root()
        diag = self._calcular_diagnostico()
        wifi_candidatos, usb_candidatos = _detect_network_adapters()
        cloudflared_path = _buscar_cloudflared()
        chequeo_previo = self._chequeo_previo_instalacion(proyecto)

        lineas = [
            "Chi.Bio Nexus — Reporte de diagnostico (Panel de Control PC)",
            f"Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Carpeta del proyecto: {proyecto}",
            "",
            "--- DIAGNOSTICO POR ESLABON ---",
            *diag["lineas"],
            "",
            "--- SERVICIOS NSSM ---",
            f"ChibioCamera: {_service_status('ChibioCamera')}",
            f"ChibioTunnel: {_service_status('ChibioTunnel')}",
            "",
            "--- RED ---",
            f"Indices configurados ahora -> WiFi={self.wifi_index}, BBB(USB)={self.usb_index}",
            "Adaptadores WiFi detectados: " + (
                "; ".join(self._nombre_adaptador(a) for a in wifi_candidatos)
                if wifi_candidatos else "(ninguno)"
            ),
            "Adaptadores USB/BBB detectados: " + (
                "; ".join(self._nombre_adaptador(a) for a in usb_candidatos)
                if usb_candidatos else "(ninguno)"
            ),
            "",
            "--- CLOUDFLARED ---",
            f"cloudflared.exe: {cloudflared_path or '(no encontrado en PATH ni ubicaciones tipicas)'}",
            "",
            "--- QUE YA ESTA INSTALADO EN ESTE PC ---",
            *chequeo_previo,
        ]
        contenido = "\n".join(lineas)

        def guardar():
            nombre_sugerido = f"chibio_reporte_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            ruta = filedialog.asksaveasfilename(
                title="Guardar reporte de diagnóstico",
                initialfile=nombre_sugerido,
                defaultextension=".txt",
                filetypes=[("Texto", "*.txt")],
            )
            if not ruta:
                self._set_log("Reporte cancelado (no se guardó).")
                return
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                self._set_log(f"Reporte guardado: {ruta}")
                self._msg_info("Reporte generado", f"Guardado en:\n{ruta}")
            except Exception as e:
                self._set_log("Error guardando el reporte.")
                self._msg_error("Error al guardar", str(e))

        self.after(0, guardar)

    # ------------------------------------------------------------------
    # Indices de red: comprobar / configurar / compartir (3 pasos separados)
    # ------------------------------------------------------------------
    def _refresh_indices_label(self):
        self.wifi_idx_label.configure(text=str(self.wifi_index))
        self.usb_idx_label.configure(text=str(self.usb_index))

    @staticmethod
    def _nombre_adaptador(a):
        return f"{a.get('Name')}  (ifIndex={a.get('ifIndex')}, {a.get('Status')})"

    def _accion_comprobar_indices(self):
        """Solo detecta y muestra lo que hay — no cambia nada."""
        self._set_log("Comprobando adaptadores de red...")
        threading.Thread(target=self._comprobar_indices_worker, daemon=True).start()

    def _comprobar_indices_worker(self):
        wifi_candidates, usb_candidates = _detect_network_adapters()

        def mostrar():
            self._set_log("Comprobación lista.")
            texto = "Adaptadores WiFi encontrados:\n"
            texto += (
                "\n".join("  - " + self._nombre_adaptador(a) for a in wifi_candidates)
                if wifi_candidates else "  - (ninguno)"
            )
            texto += "\n\nAdaptadores USB (BeagleBone) encontrados:\n"
            texto += (
                "\n".join("  - " + self._nombre_adaptador(a) for a in usb_candidates)
                if usb_candidates else "  - (ninguno — conecta el cable USB a la BeagleBone)"
            )
            texto += (
                f"\n\nÍndices configurados actualmente:  WiFi={self.wifi_index}  ·  BBB={self.usb_index}"
            )
            self._msg_info("Adaptadores de red detectados", texto)

        self.after(0, mostrar)

    def _accion_configurar_indices(self):
        """Aplica automaticamente si la deteccion es 1:1; si no, abre edicion manual."""
        self._set_log("Detectando para configurar índices...")
        threading.Thread(target=self._configurar_indices_worker, daemon=True).start()

    def _configurar_indices_worker(self):
        wifi_candidates, usb_candidates = _detect_network_adapters()

        def aplicar():
            if len(wifi_candidates) == 1 and len(usb_candidates) == 1:
                with self._indices_lock:
                    self.wifi_index = wifi_candidates[0]["ifIndex"]
                    self.usb_index = usb_candidates[0]["ifIndex"]
                self._refresh_indices_label()
                self._guardar_estado_local()
                self._set_log(
                    f"Índices aplicados automáticamente: WiFi={self.wifi_index}, "
                    f"USB={self.usb_index}."
                )
            else:
                self._abrir_dialogo_indices(wifi_candidates, usb_candidates)

        self.after(0, aplicar)

    def _abrir_dialogo_indices(self, wifi_candidates, usb_candidates):
        """Ventana para fijar los índices a mano cuando la deteccion no es 1:1."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurar índices manualmente")
        dlg.configure(fg_color=COLOR["s1"])
        self._set_dialog_icon(dlg)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        pad = {"padx": 16, "pady": 7}

        info = "Windows encontró varios adaptadores compatibles. Ingresa el índice correcto para cada uno:\n\n"
        info += "Adaptadores WiFi disponibles:\n" + (
            "\n".join("  - " + self._nombre_adaptador(a) for a in wifi_candidates)
            if wifi_candidates else "  - (ninguno detectado)"
        )
        info += "\n\nAdaptadores USB (BeagleBone) disponibles:\n" + (
            "\n".join("  - " + self._nombre_adaptador(a) for a in usb_candidates)
            if usb_candidates else "  - (ninguno — conecta el cable USB a la BeagleBone)"
        )
        ctk.CTkLabel(
            dlg, text=info, font=_font(F_UI, 12), text_color=COLOR["tx2"],
            justify="left", anchor="w",
        ).pack(fill="x", **pad)

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", **pad)

        ctk.CTkLabel(form, text="Índice WiFi:", font=_font(size=12),
                     text_color=COLOR["tx2"]).grid(row=0, column=0, sticky="w", pady=6)
        wifi_entry = ctk.CTkEntry(form, font=_font(F_MONO, 12), width=110, corner_radius=9,
                                   fg_color=COLOR["s2"], text_color=COLOR["tx"], border_width=0)
        wifi_entry.insert(0, str(self.wifi_index))
        wifi_entry.grid(row=0, column=1, padx=9, pady=6)

        ctk.CTkLabel(form, text="Índice BeagleBone (USB):", font=_font(size=12),
                     text_color=COLOR["tx2"]).grid(row=1, column=0, sticky="w", pady=6)
        usb_entry = ctk.CTkEntry(form, font=_font(F_MONO, 12), width=110, corner_radius=9,
                                  fg_color=COLOR["s2"], text_color=COLOR["tx"], border_width=0)
        usb_entry.insert(0, str(self.usb_index))
        usb_entry.grid(row=1, column=1, padx=9, pady=6)

        def guardar():
            try:
                with self._indices_lock:
                    self.wifi_index = int(wifi_entry.get().strip())
                    self.usb_index = int(usb_entry.get().strip())
            except ValueError:
                self._msg_error("Valor invalido", "Los índices deben ser numeros enteros.")
                return
            self._refresh_indices_label()
            self._guardar_estado_local()
            self._set_log(
                f"Índices configurados manualmente: WiFi={self.wifi_index}, "
                f"USB={self.usb_index}."
            )
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(pady=(5, 14))
        self._make_button(btns, "Guardar", guardar, width=120).pack(side="left", padx=5)
        self._make_button(btns, "Cancelar", dlg.destroy, width=120).pack(side="left", padx=5)

    def _accion_compartir_red(self):
        """Corre el script SOLO con los indices ya configurados — no detecta nada aqui.

        Si el indice configurado no corresponde a un adaptador real (ej. BBB
        desconectada), aborta con un mensaje claro en vez de lanzar el script
        elevado y dejar que falle con errores CIM crudos.
        """
        self._set_log("Verificando que los índices configurados existan...")
        threading.Thread(target=self._compartir_red_worker, daemon=True).start()

    def _compartir_red_worker(self):
        wifi_ok = _adapter_exists(self.wifi_index)
        usb_ok = _adapter_exists(self.usb_index)

        if not wifi_ok or not usb_ok:
            problemas = []
            if not wifi_ok:
                problemas.append(f"El adaptador WiFi (índice {self.wifi_index}) no está disponible.")
            if not usb_ok:
                problemas.append(f"La BeagleBone no está conectada por USB (índice {self.usb_index}).")
            mensaje = (
                "No se puede compartir la red:\n\n"
                + "\n".join(f"• {p}" for p in problemas)
                + "\n\nConecta los dispositivos necesarios, ve a Índices y vuelve a "
                  "ejecutar 'Comprobar índices' y 'Configurar índices' antes de continuar."
            )

            def avisar():
                self._set_log("No se puede compartir la red. Revisa los adaptadores.")
                self._msg_warn("No se puede compartir la red", mensaje)

            self.after(0, avisar)
            return

        self.after(0, lambda: self._set_log(
            "Compartiendo red (puede pedir permiso de administrador)..."
        ))
        _run_ps1_elevated(
            "compartir_red_beaglebone.ps1",
            extra_args=[f"-WifiIndex {self.wifi_index}", f"-UsbIndex {self.usb_index}"],
        )
        self.after(0, lambda: self._set_log("Red compartida. Verifica el estado."))
        self.after(200, self._verificar_estado)

    def _accion_iniciar_servicios(self):
        self._set_log("Iniciando servicios PC (puede pedir permiso de administrador)...")
        self._run_async(
            lambda: _run_ps1_elevated("activar_servicios_pc.ps1"),
            "Servicios iniciados. Verifica el estado.",
        )

    def _accion_detener_servicios(self):
        self._set_log("Deteniendo servicios PC (puede pedir permiso de administrador)...")
        self._run_async(
            lambda: _run_ps1_elevated("desactivar_servicios_pc.ps1"),
            "Servicios detenidos. Verifica el estado.",
        )

    def _leer_config_pc(self, proyecto):
        """Lee config_pc.py (si existe) y devuelve dict con TUNNEL_NAME/CHIBIO_HOSTNAME/CAMERA_HOSTNAME."""
        path = os.path.join(proyecto, "config_pc.py")
        valores = {"TUNNEL_NAME": "", "CHIBIO_HOSTNAME": "", "CAMERA_HOSTNAME": ""}
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    texto = f.read()
                for clave in valores:
                    m = re.search(rf"{clave}\s*=\s*[\"']([^\"']+)[\"']", texto)
                    if m:
                        valores[clave] = m.group(1)
            except Exception:
                pass
        return valores

    def _cargar_config_urls(self):
        cfg = self._leer_config_pc(_project_root())
        self._tunnel_configurado = bool(cfg.get("CHIBIO_HOSTNAME"))
        self.tunnel_url = (
            f"https://{cfg['CHIBIO_HOSTNAME']}" if self._tunnel_configurado else TUNNEL_URL
        )
        self.camera_tunnel_health = (
            f"https://{cfg['CAMERA_HOSTNAME']}/health" if cfg.get("CAMERA_HOSTNAME") else CAMERA_TUNNEL_HEALTH
        )

    def _chequear_gemini_key(self):
        config_path = os.path.join(_project_root(), "config.py")
        if not os.path.isfile(config_path):
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                contenido = f.read()
            if "your_gemini_api_key_here" in contenido:
                self._set_log(
                    "Gemini API key es placeholder — edita config.py con tu key real de aistudio.google.com"
                )
        except Exception:
            pass

    def _cargar_estado_local(self):
        path = os.path.join(_project_root(), ".chibio_panel.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.wifi_index = int(data.get("wifi_index", self.wifi_index))
            self.usb_index = int(data.get("usb_index", self.usb_index))
            raw = data.get("use_tunnel", None)
            self._use_tunnel = bool(raw) if raw is not None else None
        except Exception:
            self._use_tunnel = None  # primera ejecucion

    def _guardar_estado_local(self):
        path = os.path.join(_project_root(), ".chibio_panel.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "wifi_index": self.wifi_index,
                    "usb_index": self.usb_index,
                    "use_tunnel": self._use_tunnel,
                }, f)
        except Exception:
            pass

    def _wizard_tunel(self):
        """Primera ejecucion: pregunta si el usuario usa Cloudflare Tunnel."""
        respuesta = self._msg_yesno(
            "Configuración inicial — Acceso remoto",
            "¿Necesitas acceder a Chi.Bio Nexus desde fuera de tu red local (por internet)?\n\n"
            "Sí → se mostrará la configuración del túnel Cloudflare.\n"
            "No → acceso solo dentro de la red local (más simple).\n\n"
            "Puedes cambiar esta preferencia más adelante en la sección Ajustes.",
        )
        self._use_tunnel = bool(respuesta)
        self._guardar_estado_local()

    def _cambiar_preferencia_tunel(self):
        """Alterna use_tunnel, guarda y pide reinicio."""
        nuevo = not self._use_tunnel
        accion = "activar" if nuevo else "desactivar"
        if not self._msg_yesno(
            "Cambiar preferencia de túnel",
            f"¿Confirmas {accion} el túnel Cloudflare?\n\n"
            "El cambio se aplica al reiniciar el panel.",
        ):
            return
        self._use_tunnel = nuevo
        self._guardar_estado_local()
        self._msg_info(
            "Preferencia guardada",
            f"Túnel {'activado' if nuevo else 'desactivado'}.\n"
            "Cierra y vuelve a abrir el panel para aplicar el cambio.",
        )

    def _iniciar_auto_refresh(self):
        self._auto_refresh_activo = True
        def loop():
            while self._auto_refresh_activo:
                time.sleep(30)
                if self._auto_refresh_activo:
                    self.after(0, self._verificar_estado)
        threading.Thread(target=loop, daemon=True).start()

    @staticmethod
    def _comando_existe(nombre):
        """Chequea (sin elevar) si un .exe esta en el PATH via Get-Command."""
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Command {nombre} -ErrorAction SilentlyContinue).Source"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return bool(out.stdout.strip())
        except Exception:
            return False

    def _chequeo_previo_instalacion(self, proyecto):
        """Detecta (sin instalar nada) que ya esta listo vs que va a hacer instalar_todo.ps1.

        Evita correr ~10 pasos a ciegas — el script ya es idempotente y se salta lo
        que existe, pero el usuario no sabe eso hasta que ve la consola; esto se lo
        muestra ANTES de lanzar nada.
        """
        lineas = []

        venv_python = os.path.join(proyecto, ".venv", "Scripts", "python.exe")
        lineas.append(
            "Entorno Python (.venv): ya existe" if os.path.isfile(venv_python)
            else "Entorno Python (.venv): falta -> se creara e instalaran dependencias"
        )

        config_py = os.path.join(proyecto, "config.py")
        lineas.append(
            "config.py (API key Gemini): ya existe" if os.path.isfile(config_py)
            else "config.py (API key Gemini): falta -> se va a pedir la key"
        )

        nssm_ok = self._comando_existe("nssm")
        lineas.append(
            "NSSM: ya instalado" if nssm_ok
            else "NSSM: falta -> se instalara via winget"
        )

        cloudflared_ok = bool(_buscar_cloudflared())
        lineas.append(
            "cloudflared.exe: ya instalado" if cloudflared_ok
            else "cloudflared.exe: falta -> se descargara de GitHub releases"
        )

        cert_path = os.path.join(os.path.expanduser("~"), ".cloudflared", "cert.pem")
        lineas.append(
            "Login Cloudflare (cert.pem): ya existe" if os.path.isfile(cert_path)
            else "Login Cloudflare (cert.pem): falta -> pedira login en el navegador (solo si usas tunel)"
        )

        for servicio in ("ChibioCamera", "ChibioTunnel"):
            estado = _service_status(servicio)
            lineas.append(f"Servicio {servicio}: {estado}")

        return lineas

    def _accion_instalar_todo(self):
        proyecto = _project_root()
        req_dest = os.path.join(proyecto, "requirements-windows.txt")
        if not os.path.isfile(req_dest):
            meipass = getattr(sys, "_MEIPASS", None)
            req_src = os.path.join(meipass, "requirements-windows.txt") if meipass else None
            if req_src and os.path.isfile(req_src):
                import shutil
                shutil.copy2(req_src, req_dest)
            else:
                self._msg_error(
                    "Instalar todo — abortado",
                    "No se encontro requirements-windows.txt junto a este ejecutable "
                    f"({proyecto}).\n\nColoca este .exe en la raiz del repositorio "
                    "clonado (junto a requirements-windows.txt, camera\\, scripts\\) "
                    "y vuelve a intentar.",
                )
                return

        self._set_log("Comprobando qué falta instalar...")
        threading.Thread(
            target=lambda: self._instalar_todo_tras_chequeo(proyecto), daemon=True
        ).start()

    def _instalar_todo_tras_chequeo(self, proyecto):
        lineas = self._chequeo_previo_instalacion(proyecto)
        reporte = "Estado actual de este PC antes de instalar:\n\n" + "\n".join(lineas)

        def continuar():
            self._set_log("Listo.")
            self._msg_info("Revisión previa a la instalación", reporte)
            self._continuar_instalar_todo(proyecto)

        self.after(0, continuar)

    def _continuar_instalar_todo(self, proyecto):
        usa_tunel = bool(self._use_tunnel)

        if usa_tunel:
            ok = self._abrir_dialogo_tunel(proyecto)
            if not ok:
                return
            extra_args = [f'-ProyectoPath "{proyecto}"']
        else:
            extra_args = [f'-ProyectoPath "{proyecto}"', "-SkipTunnel"]

        confirmado = self._msg_yesno(
            "Confirmar instalación",
            "Se abrirá una ventana de PowerShell con permisos de administrador.\n\n"
            "El proceso instalará automáticamente:\n"
            "  · Dependencias Python y NSSM\n"
            + (
                "  · cloudflared (se pedirá login en el navegador)\n"
                "  · Túnel Cloudflare y configuración DNS\n"
                "  · Servicios ChibioCamera y ChibioTunnel\n"
                if usa_tunel else
                "  · Servicio ChibioCamera (acceso solo en red local)\n"
            )
            + "  · Compartición de red a la BeagleBone\n\n"
            "El proceso puede tardar varios minutos. Durante la instalación se pedirá "
            + ("la API key de Gemini" + (" y el login de Cloudflare" if usa_tunel else ""))
            + ".\n\n¿Continuar?",
        )
        if not confirmado:
            return

        self._set_log("Lanzando instalar_todo.ps1 en ventana aparte...")
        threading.Thread(
            target=lambda: _run_ps1_elevated(
                "instalar_todo.ps1", wait=False,
                extra_args=extra_args,
            ),
            daemon=True,
        ).start()
        self.after(500, lambda: self._set_log(
            "instalar_todo.ps1 corriendo en su propia ventana. Revisa esa consola."
        ))

    def _abrir_dialogo_tunel(self, proyecto):
        """Pide tunel/dominio propio y los guarda en config_pc.py. Devuelve True si se guardo."""
        actuales = self._leer_config_pc(proyecto)
        resultado = {"ok": False}

        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurar Cloudflare Tunnel")
        dlg.configure(fg_color=COLOR["s1"])
        self._set_dialog_icon(dlg)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        pad = {"padx": 16, "pady": 7}
        ctk.CTkLabel(
            dlg,
            text="Ingresa los datos de tu túnel Cloudflare.\n"
                 "Esta configuración se guarda localmente en este PC.",
            font=_font(F_UI, 12), text_color=COLOR["tx2"], justify="left",
        ).pack(fill="x", **pad)

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", **pad)

        campos = {}
        etiquetas = [
            ("TUNNEL_NAME", "Nombre del túnel:"),
            ("CHIBIO_HOSTNAME", "Dominio Chi.Bio Nexus:"),
            ("CAMERA_HOSTNAME", "Dominio de la cámara:"),
        ]
        for i, (clave, etiqueta) in enumerate(etiquetas):
            ctk.CTkLabel(form, text=etiqueta, font=_font(size=12),
                         text_color=COLOR["tx2"]).grid(row=i, column=0, sticky="w", pady=6)
            entry = ctk.CTkEntry(form, font=_font(F_MONO, 12), width=280, corner_radius=9,
                                  fg_color=COLOR["s2"], text_color=COLOR["tx"], border_width=0)
            entry.insert(0, actuales.get(clave, ""))
            entry.grid(row=i, column=1, padx=9, pady=5)
            campos[clave] = entry

        def guardar():
            valores = {clave: campos[clave].get().strip() for clave in campos}
            for k in ("CHIBIO_HOSTNAME", "CAMERA_HOSTNAME"):
                valores[k] = valores[k].removeprefix("https://").removeprefix("http://").rstrip("/")
            if not all(valores.values()):
                self._msg_error("Faltan datos", "Completa los 3 campos (o cancela y elige 'No' al tunel).")
                return
            contenido = (
                "# config_pc.py — generado por el Panel de Control. No se sube a git.\n"
                f'TUNNEL_NAME = "{valores["TUNNEL_NAME"]}"\n'
                f'CHIBIO_HOSTNAME = "{valores["CHIBIO_HOSTNAME"]}"\n'
                f'CAMERA_HOSTNAME = "{valores["CAMERA_HOSTNAME"]}"\n'
            )
            with open(os.path.join(proyecto, "config_pc.py"), "w", encoding="utf-8") as f:
                f.write(contenido)
            resultado["ok"] = True
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(pady=(5, 14))
        self._make_button(btns, "Guardar", guardar, variant="primary", width=120).pack(side="left", padx=5)
        self._make_button(btns, "Cancelar", dlg.destroy, width=120).pack(side="left", padx=5)

        self.wait_window(dlg)
        if resultado["ok"]:
            self._cargar_config_urls()
        return resultado["ok"]

    # ------------------------------------------------------------------
    # Tour guiado: ventana flotante que recorre las secciones del panel
    # ------------------------------------------------------------------
    def _iniciar_tour(self):
        if hasattr(self, "_tour_dlg") and self._tour_dlg and self._tour_dlg.winfo_exists():
            self._tour_dlg.focus()
            return
        self._tour_paso = 0
        self._crear_ventana_tour()
        self._tour_goto(0)

    def _crear_ventana_tour(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Tour guiado")
        dlg.configure(fg_color=COLOR["s1"])
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        self._set_dialog_icon(dlg)
        self._tour_dlg = dlg

        # Header: barra de acento verde + "Paso X de Y" prominente
        header = ctk.CTkFrame(dlg, fg_color=COLOR["s2"], corner_radius=0, height=42)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkFrame(header, fg_color=COLOR["gr"], corner_radius=0, width=4).pack(
            side="left", fill="y"
        )
        self._tour_step_lbl = ctk.CTkLabel(
            header, text="", font=_font(F_MONO, 11, "bold"), text_color=COLOR["gr"],
        )
        self._tour_step_lbl.pack(side="left", padx=14)

        # Contenido: barra verde izquierda + título y body
        content = ctk.CTkFrame(dlg, fg_color="transparent")
        content.pack(fill="both", expand=True)

        ctk.CTkFrame(content, fg_color=COLOR["gr_d"], corner_radius=0, width=3).pack(
            side="left", fill="y", padx=(16, 0), pady=14,
        )

        text_col = ctk.CTkFrame(content, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True, padx=(12, 16), pady=14)

        self._tour_title_lbl = ctk.CTkLabel(
            text_col, text="", font=_font(F_UI, 17, "bold"), text_color=COLOR["tx"],
            wraplength=300, justify="left", anchor="w",
        )
        self._tour_title_lbl.pack(anchor="w", pady=(0, 10))

        self._tour_body_lbl = ctk.CTkLabel(
            text_col, text="", font=_font(F_UI, 13), text_color=COLOR["tx2"],
            wraplength=300, justify="left", anchor="w",
        )
        self._tour_body_lbl.pack(anchor="w", fill="both", expand=True)

        # Footer
        btns = ctk.CTkFrame(dlg, fg_color=COLOR["s2"], corner_radius=0, height=54)
        btns.pack(fill="x", side="bottom")
        btns.pack_propagate(False)

        self._tour_prev_btn = self._make_button(
            btns, "← Anterior", lambda: self._tour_goto(self._tour_paso - 1), width=110,
        )
        self._tour_prev_btn.pack(side="left", padx=(10, 4), pady=10)

        self._tour_next_btn = self._make_button(
            btns, "Siguiente →", lambda: self._tour_goto(self._tour_paso + 1),
            variant="primary", width=126,
        )
        self._tour_next_btn.pack(side="left", padx=4, pady=10)

        self._make_button(btns, "Cerrar", dlg.destroy, width=80).pack(
            side="right", padx=10, pady=10,
        )

        self.update_idletasks()
        mx, my = self.winfo_x(), self.winfo_y()
        mw, mh = self.winfo_width(), self.winfo_height()
        dlg.geometry(f"370x340+{mx + mw - 394}+{my + mh - 370}")

    def _tour_goto(self, paso):
        total = len(TOUR_STEPS)
        paso = max(0, min(paso, total - 1))
        self._tour_paso = paso
        step = TOUR_STEPS[paso]

        self._mostrar_pagina(step["pagina"])
        self._tour_step_lbl.configure(text=f"Paso {paso + 1} de {total}")
        self._tour_title_lbl.configure(text=step["titulo"])
        self._tour_body_lbl.configure(text=step["texto"])

        if paso > 0:
            self._tour_prev_btn.configure(
                state="normal", text_color=COLOR["tx2"],
                fg_color=COLOR["s2"], border_color=COLOR["bd"],
            )
        else:
            self._tour_prev_btn.configure(
                state="disabled", text_color=COLOR["tx3"],
                fg_color=COLOR["bg"], border_color=COLOR["bd"],
            )
        if paso == total - 1:
            self._tour_next_btn.configure(
                text="✓ Finalizar",
                command=self._tour_dlg.destroy,
                fg_color=COLOR["gr_d"],
                hover_color=COLOR["gr"],
                border_color=COLOR["gr"],
            )
        else:
            self._tour_next_btn.configure(
                text="Siguiente →",
                command=lambda: self._tour_goto(self._tour_paso + 1),
                fg_color=COLOR["gr_d"],
                hover_color=COLOR["gr"],
                border_color=COLOR["gr"],
            )

    def _run_async(self, fn, mensaje_final):
        def worker():
            try:
                fn()
                self.after(0, lambda: self._set_log(mensaje_final))
            except Exception as e:
                self.after(0, lambda err=str(e): self._set_log(f"Error: {err}"))
            self.after(200, self._verificar_estado)

        threading.Thread(target=worker, daemon=True).start()

    def _abrir_navegador(self):
        # Túnel primero: si está configurado y el origen responde, es la URL pública.
        if self._tunnel_configurado and _http_check(self.tunnel_url):
            webbrowser.open(self.tunnel_url)
            self._set_log(f"Abriendo {self.tunnel_url} (túnel disponible).")
        elif _tcp_check(LOCAL_HOST, LOCAL_PORT):
            webbrowser.open(LOCAL_URL)
            self._set_log(f"Abriendo {LOCAL_URL} (LAN).")
        else:
            if self._tunnel_configurado:
                self._set_log(
                    "Nexus no disponible: túnel no responde y BBB sin conexión LAN."
                )
            else:
                self._set_log(
                    "BBB no responde en LAN (192.168.7.2:5000). Verifica cable USB y red compartida."
                )

    def _abrir_camara_navegador(self):
        if _http_check(CAMERA_LOCAL_HEALTH):
            webbrowser.open("http://127.0.0.1:8000/preview")
            self._set_log("Abriendo visor de cámara WebRTC en el navegador.")
        else:
            self._set_log("Servidor de cámara no disponible. Inicia los servicios primero.")


def main():
    app = PanelControl()
    app.mainloop()


if __name__ == "__main__":
    main()
