# Chi.Bio Nexus

Plataforma web de control y monitoreo remoto para biorreactores [Chi.Bio](https://chi.bio/) a escala milimétrica.

---

## ¿Qué hace?

- Control en tiempo real de actuadores: bombas, agitación, temperatura, LEDs, UV
- Visualización de OD, tasa de crecimiento (μ), temperatura y actividad de bombas
- Editor visual de protocolos de cultivo (**Architect**) con generación de código Python via IA
- Análisis de protocolos activos con Google Gemini
- Streaming de cámara en tiempo real via WebRTC
- Acceso remoto desde cualquier navegador vía Cloudflare Tunnel

---

## Inicio rápido

### Opción A — Simulador (sin hardware)

Prueba la interfaz completa en cualquier PC, sin BeagleBone ni dispositivo Chi.Bio.

```bash
# 1. Clonar el repositorio
git clone https://github.com/primbiolab/chibio_nexus
cd chibio_nexus

# 2. Instalar dependencias
pip install -r requirements-windows.txt

# 3. Lanzar el simulador (abre el navegador automáticamente)
python lanzador_dev.py
```

El simulador genera 3 reactores (M0, M1, M2) con datos biológicos realistas y fluctuantes.
Toda la UI es funcional: gráficas, Architect, cambio de tema, etc.

---

### Opción B — Despliegue real en BeagleBone Black

#### Requisitos de hardware
- [BeagleBone Black](https://beagleboard.org/black) con Debian Linux
- Dispositivo Chi.Bio conectado por I2C
- PC Windows con conexión USB a la BeagleBone

#### 1. Obtener una API key de Gemini

Ve a [aistudio.google.com/apikey](https://aistudio.google.com/apikey) y crea una clave gratuita.

#### 2. Configurar la red del PC

La BeagleBone no tiene WiFi propio. Su acceso a internet se realiza compartiendo la red del PC via USB.

Ejecutar como Administrador (doble clic sobre `iniciar_red.bat` → "Ejecutar como administrador"):

```
iniciar_red.bat
```

Verificar que el adaptador del BeagleBone tiene asignada la dirección `192.168.7.1`:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, IPAddress | Format-Table
```

> Si los índices de interfaz de red de tu equipo difieren de los valores por defecto (16 para WiFi, 35 para USB), editar `scripts/compartir_red_beaglebone.ps1` y actualizar `$INDEX_WIFI` y `$INDEX_USB` antes de ejecutar.

#### 3. Copiar el proyecto a la BeagleBone

```bash
scp -r chibio_nexus/ root@192.168.7.2:/root/chibio/
```

#### 4. Instalar y configurar (en la BeagleBone, via PuTTY a 192.168.7.2)

```bash
cd /root/chibio
bash scripts/setup_beaglebone.sh
```

El script instala las dependencias y crea `config.py`. Editar ese archivo con la API key:

```bash
nano config.py
```

```python
GEMINI_API_KEY = "tu_api_key_aqui"
```

#### 5. Configurar la red en la BeagleBone

```bash
sudo ip route add default via 192.168.7.1 dev usb0
sudo sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'
ping -c 3 github.com
```

#### 6. Iniciar el servidor

```bash
bash scripts/cb.sh
```

#### 7. Abrir en el navegador

```
http://192.168.7.2:5000
```

---

### Servidor de cámara (opcional, Windows)

Chi.Bio Nexus puede mostrar un stream de video en vivo del biorreactor via WebRTC. Requiere una cámara USB conectada al PC Windows.

**Instalar dependencias** (si no se hizo en el paso de simulador):

```bash
pip install -r requirements-windows.txt
```

**Iniciar el servidor de cámara:**

```powershell
.\scripts\lanzador_camara.ps1
```

El servidor queda corriendo en `http://localhost:8000`. Para verificar que arrancó correctamente, abrir `http://localhost:8000/health` en el navegador: debe mostrar un JSON con `status`, `fps` y `peers`.

Para acceso remoto, exponer el puerto 8000 mediante Cloudflare Tunnel. Consultar la [documentación oficial de Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

---

## Estructura del proyecto

```
chibio_nexus/
├── app.py                     ← Servidor Flask (BeagleBone)
├── mock_server.py             ← Servidor simulado (demo sin hardware)
├── lanzador_dev.py            ← Lanzador del simulador
├── iniciar_red.bat            ← Configuración de red WiFi → BeagleBone
├── config.example.py          ← Template de configuración
├── requirements.txt           ← Dependencias BeagleBone
├── requirements-windows.txt   ← Dependencias PC Windows
├── docs/
│   └── manualusuario.txt      ← Fuente del manual de usuario
├── camera/
│   └── server.py              ← Servidor de cámara WebRTC (Windows)
├── scripts/
│   ├── cb.sh                  ← Inicio del servidor en BeagleBone
│   ├── setup_beaglebone.sh    ← Instalación automática en BeagleBone
│   ├── compartir_red_beaglebone.ps1  ← Configuración de red (Windows)
│   ├── lanzador_camara.ps1    ← Lanzador cámara (Windows)
│   └── start_tunnel.ps1       ← Lanzador Cloudflare Tunnel (Windows)
├── templates/
│   ├── index.html             ← Interfaz principal (Nexus)
│   └── architect.html         ← Editor de protocolos (Architect)
└── static/
    ├── css/
    │   ├── nexus.css
    │   └── architect.css
    └── js/
        ├── nexus.js
        └── architect.js
```

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python + Flask, Gunicorn |
| Hardware | BeagleBone Black (ARM Cortex-A8, Debian Linux 32-bit) |
| Frontend | Vanilla JS + jQuery, Google Charts |
| IA | Google Gemini 2.5 Flash Lite |
| Cámara | FastAPI + aiortc + OpenCV, WebRTC H.264 |
| Acceso remoto | Cloudflare Tunnel |

---

## Reiniciar el servidor (BeagleBone)

```bash
pkill -f gunicorn && sleep 2 && bash scripts/cb.sh
```

Los cambios en `static/css/` y `static/js/` no requieren reiniciar: solo `Ctrl+Shift+R` en el navegador.
Los cambios en `templates/` y `app.py` sí requieren reiniciar.

---

## Autor

Desarrollado por **Juan David Romero Montes**.
Basado en el hardware open-source [Chi.Bio](https://chi.bio/) (Harrison & Dunlop, 2020).
