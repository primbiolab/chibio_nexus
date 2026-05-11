# Chi.Bio Nexus

Plataforma web de control y monitoreo remoto para biorreactores [Chi.Bio](https://chi.bio/) a escala milimétrica.  
Desarrollada en **Primbiolab — Universidad Nacional de Colombia**, bajo la dirección del Prof. Francisco Burgos.

---

## ¿Qué hace?

- Control en tiempo real de actuadores: bomba, agitación, temperatura, LEDs, UV
- Visualización de OD, tasa de crecimiento (μ), temperatura y bombas
- Editor visual de protocolos de cultivo (**Architect**) con generación de código Python via IA
- Análisis de protocolos con Google Gemini
- Streaming de cámara en tiempo real
- Acceso remoto desde cualquier navegador (vía Cloudflare Tunnel)

---

## Inicio rápido

Hay dos formas de usar este repositorio:

### Opción A — Simulador (sin hardware)

Prueba la interfaz completa en cualquier PC, sin BeagleBone ni dispositivo Chi.Bio.

```bash
# 1. Clonar el repositorio
git clone https://github.com/primbiolab/chibio_nexus
cd chibio_nexus

# 2. Instalar dependencias
pip install -r requirements-dev.txt

# 3. Lanzar el simulador (abre el navegador automáticamente)
python lanzador_dev.py
```

El simulador genera 3 reactores (M0, M1, M2) con datos biológicos realistas y fluctuantes.  
Toda la UI es funcional: gráficas, Architect, cambio de tema, etc.

---

### Opción B — Despliegue real en BeagleBone Black

#### Requisitos de hardware
- [BeagleBone Black](https://beagleboard.org/black) con Debian Linux
- Dispositivo Chi.Bio conectado por I2C/SPI
- PC con conexión USB a la BeagleBone (`192.168.7.2`)

#### 1. Obtener una API key de Gemini

Ve a [aistudio.google.com/apikey](https://aistudio.google.com/apikey) y crea una clave gratuita.

#### 2. Copiar el proyecto a la BeagleBone

```bash
scp -r chibio_nexus/ root@192.168.7.2:/root/chibio/
```

#### 3. Instalar y configurar (en la BeagleBone, via PuTTY)

```bash
cd /root/chibio
bash scripts/setup_beaglebone.sh
```

El script instala las dependencias y crea `config.py`. Luego edita ese archivo con tu API key:

```bash
nano config.py
```

```python
GEMINI_API_KEY = "tu_api_key_aqui"
```

#### 4. Iniciar el servidor

```bash
bash scripts/cb.sh
```

#### 5. Abrir en el navegador (desde tu PC)

```
http://192.168.7.2:5000
```

---

### Servidor de cámara (opcional, Windows)

Chi.Bio Nexus puede mostrar un stream de video en vivo del biorreactor. Esto requiere una cámara conectada al PC Windows (no a la BeagleBone) y un servidor independiente que transmite el video.

#### ¿Por qué corre en el PC y no en la BeagleBone?

La BeagleBone Black no tiene la potencia de procesamiento suficiente para capturar y transmitir video en tiempo real. Por eso el servidor de cámara corre en el mismo PC desde el que controlas el sistema.

#### Configuración

**1. Conectar una cámara USB** al PC Windows.

**2. Instalar dependencias:**

```bash
pip install -r requirements-camera.txt
```

**3. Iniciar el servidor de cámara:**

```powershell
.\scripts\lanzador_camara.ps1
```

El servidor queda corriendo en `http://localhost:5001`. La interfaz Nexus lo detecta automáticamente si está activo.

#### Acceso remoto a la cámara

Por defecto, el stream de cámara solo es accesible desde tu red local. Si quieres verlo desde cualquier lugar (acceso remoto), necesitas exponer ese puerto a internet de forma segura.

La solución recomendada es **Cloudflare Tunnel**, una herramienta gratuita que crea una URL pública (`https://...`) que apunta a tu servidor local sin necesidad de abrir puertos en el router.

1. Descarga `cloudflared` desde [developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
2. Ejecuta en la terminal:
   ```bash
   cloudflared tunnel --url http://localhost:5001
   ```
3. Cloudflare te dará una URL pública temporal. Úsala en la configuración de cámara dentro de Nexus.

> Para una URL fija y permanente (no temporal), se puede configurar un túnel nombrado en Cloudflare. Consulta la [documentación oficial](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

---

## Estructura del proyecto

```
chibio_nexus/
├── app.py                    ← Servidor Flask (BeagleBone)
├── mock_server.py            ← Servidor simulado (demo sin hardware)
├── lanzador_dev.py           ← Lanzador del simulador
├── config.example.py         ← Template de configuración
├── requirements.txt          ← Deps BeagleBone
├── requirements-camera.txt   ← Deps servidor de cámara
├── requirements-dev.txt      ← Deps simulador
├── camera/
│   └── serverCamara.py       ← Servidor de cámara (Windows)
├── scripts/
│   ├── cb.sh                 ← Inicio del servidor en BeagleBone
│   ├── setup_beaglebone.sh   ← Instalación automática
│   └── lanzador_camara.ps1   ← Lanzador cámara (Windows)
├── templates/
│   ├── index.html            ← Interfaz principal (Nexus)
│   └── architect.html        ← Editor de protocolos (Architect)
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
| Hardware | BeagleBone Black (ARM Cortex-A8, Debian Linux) |
| Frontend | Vanilla JS + jQuery, Google Charts |
| IA | Google Gemini 2.5 Flash Lite |
| Cámara | OpenCV + Flask (servidor independiente) |
| Acceso remoto | Cloudflare Tunnel |

---

## Reiniciar el servidor (BeagleBone)

```bash
pkill -f gunicorn && sleep 2 && bash scripts/cb.sh
```

Los cambios en `static/css/` y `static/js/` no requieren reiniciar — solo `Ctrl+Shift+R` en el navegador.  
Los cambios en `templates/` y `app.py` sí requieren reiniciar.

---

## Créditos

Desarrollado por el grupo **Primbiolab**  
Universidad Nacional de Colombia  
Director: Prof. Francisco Burgos

Basado en el hardware open-source [Chi.Bio](https://chi.bio/) (Harrison & Dunlop, 2020).
