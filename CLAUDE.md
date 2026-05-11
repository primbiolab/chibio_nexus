# Chi.Bio Nexus — Contexto del Proyecto para Claude Code

## ¿Qué es este proyecto?

Chi.Bio Nexus es una plataforma web de control de biorreactores de laboratorio a escala milimétrica.
Desarrollada en **Primbiolab, Universidad Nacional de Colombia**, bajo la dirección del Prof. Francisco Burgos.
Permite controlar, monitorear y programar biorreactores de forma remota desde un navegador, con
visualización en tiempo real, editor visual de protocolos, streaming de cámara y análisis por IA (Google Gemini).

---

## Estructura de carpetas

```
/root/chibio/                   ← raíz en el BeagleBone
├── app.py                      ← backend Flask principal (BeagleBone)
├── mock_server.py              ← servidor de desarrollo local (Windows, sin hardware)
├── protocolo.py                ← protocolo activo de cultivo (leído/escrito por Flask)
├── cb.sh                       ← script de inicio del servidor en BeagleBone
├── templates/
│   ├── index.html              ← Chi.Bio Nexus: interfaz principal
│   └── architect.html          ← editor visual de protocolos (sin topbar propio)
└── static/
    ├── HTMLScripts.js          ← script original Chi.Bio — NO MODIFICAR
    ├── css/
    │   ├── nexus.css           ← estilos de index.html
    │   └── architect.css       ← estilos de architect.html
    └── js/
        ├── nexus.js            ← lógica de index.html
        └── architect.js        ← lógica de architect.html
```

El servidor de cámara (`camera_server.py`) corre **en el PC Windows** por separado, en el puerto 5001.

---

## Hardware y red

| Componente | Detalle |
|---|---|
| Hardware | BeagleBone Black — ARM Cortex-A8, Debian Linux, 32-bit |
| IP USB | `192.168.7.2`, puerto Flask `5000` |
| Producción | `https://chibio.primbiolab.org` (Cloudflare Tunnel) |
| Cámara | `https://camera.primbiolab.org` (Cloudflare Tunnel `chibio-camera`) |
| Reinicio servidor | `pkill -f gunicorn && sleep 2 && bash cb.sh` |

**Flask escucha SOLO en `192.168.7.2:5000`** — nunca en `0.0.0.0` ni `localhost` en producción.

---

## Stack tecnológico

### Backend (`app.py`)
- Python + Flask, servido con Gunicorn
- Google Gemini 2.5 Flash Lite — API key **solo en `app.py`**, nunca en frontend
- Billing activo en Google Cloud — alertar si un cambio aumenta el consumo de Gemini

### Frontend (`index.html` + `nexus.css` + `nexus.js`)
- Vanilla JS + HTML/CSS — **sin frameworks** (React, Vue, Angular están prohibidos)
- jQuery 3.2.1 para DOM y AJAX
- Google Charts para visualización (CDN)
- Font Awesome 6.5 para íconos (CDN)
- Fuentes: Nunito, IBM Plex Mono, Bebas Neue (Google Fonts)
- Variables CSS con prefijo `--bg`, `--gr`, `--bl`, `--s1`, `--s2`, etc.
- Layout: 3 columnas (252px | flex | 295px) + topbar sticky 50px
- Móvil: tabs inferiores fijos (Setup / Gráficas / Avanzado / Actuadores)

### Frontend (`architect.html` + `architect.css` + `architect.js`)
- **Sin topbar propio** — el topbar lo provee el Nexus vía iframe
- Fuentes propias: Space Grotesk, Syne Mono, Outfit
- Variables CSS propias: `--accent`, `--surface`, `--surface2`, `--surface3`, `--text`, `--text2`, etc.
- **CRÍTICO: el namespace CSS del Architect es DISTINTO al del Nexus. NUNCA mezclarlos.**

---

## Endpoints Flask principales

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Sirve `index.html` con `sysData` del reactor activo |
| GET | `/architect` | Sirve `architect.html` |
| GET | `/getSysdata/` | Retorna JSON con estado completo del sistema |
| POST | `/analyzeProtocol/` | Lee `protocolo.py`, llama a Gemini → `{analysis, code}` |
| POST | `/generateProtocol/` | Recibe `{prompt}` → llama a Gemini → `{ast}` |
| POST | `/injectProtocol/` | Recibe `{code}` Python compilado → guarda en `protocolo.py` |
| POST | `/changeDevice/<M>` | Cambia el reactor activo en la UI |
| POST | `/Experiment/<on>/<M>` | Inicia o detiene el experimento |
| POST | `/SetOutputTarget/<param>/0/<val>` | Setea valor objetivo de un actuador |
| POST | `/SetOutputOn/<param>/2/0` | Alterna on/off de un actuador |

Al agregar endpoints: método explícito, ruta con `/` al final, respuesta JSON, `try/except` con `jsonify({"error": str(e)})`.

---

## Comunicación Nexus ↔ Architect

- Architect carga dentro de `<iframe src="/architect">` en el Nexus
- Nexus → Architect: `postMessage({ type:'archCmd', cmd, val }, window.location.origin)`
- Architect → Nexus: `postMessage({ type:'archState', canSend, safetyOk }, window.location.origin)`
- Tema claro/oscuro: Nexus propaga al iframe via `postMessage({ type:'setTheme', theme })`
- **SIEMPRE validar `e.origin !== window.location.origin` antes de procesar mensajes entrantes**
- **NUNCA usar `'*'` como targetOrigin**

---

## Reglas críticas — leer antes de cualquier modificación

1. **Leer los archivos completos antes de escribir una línea.** Pueden haber cambiado desde la última sesión.
2. **Solo modificar lo que fue pedido explícitamente.** Si algo relacionado debe cambiarse, mencionarlo — no tocarlo.
3. **Cuando se elimina un elemento HTML con `id`, buscar y actualizar TODAS las referencias a ese `id` en JS antes de entregar.** Los errores JS silenciosos por `getElementById` nulo rompen toda la función que los contiene.
4. **CSS Nexus**: variables `--bg`, `--gr`, `--bl`, `--s1`, `--s2`, `--bd`, `--tx`, `--tx2`, `--tx3`, `--bl`, `--f-mono`
5. **CSS Architect**: variables `--accent`, `--surface`, `--surface2`, `--surface3`, `--border`, `--text`, `--text2`, `--text3`
6. **Nunca mezclar los namespaces CSS de Nexus y Architect.**
7. **La API key de Gemini vive solo en `app.py`.** Nunca en frontend, logs ni comentarios.
8. **BeagleBone es ARM 32-bit.** Verificar compatibilidad ARM de cualquier dependencia Python nueva.
9. **No usar `0.0.0.0` como host en `app.py`.** Siempre `192.168.7.2`.
10. **No introducir frameworks frontend.** El proyecto usa Vanilla JS + jQuery intencionalmente.

---

## Convenciones de código

```
Python:     snake_case funciones/variables, UPPER_SNAKE_CASE constantes
JavaScript: camelCase variables/funciones, PascalCase constructores
HTML IDs:   kebab-case descriptivos (ej: exp-status-pill, pump-row-1)
CSS clases: kebab-case (ej: btn-start, pump-row)
```

AJAX siempre asíncrono con manejo de error explícito. Nunca fallar silenciosamente — siempre dar feedback visual al usuario.

---

## Módulos funcionales principales

**Nexus (`nexus.js`):**
- `getSysData()`: polling cada 2s a `/getSysdata/` — función más crítica del sistema
- `updateData(data)`: actualiza toda la UI con los datos recibidos — la más llamada, mantenerla eficiente
- `_drawAllCharts(data)`: renderiza gráficas OD, μ, temperatura y bombas
- `archCmd(cmd, val)`: envía comandos al iframe del Architect
- `toggleTheme()`: alterna tema y propaga al iframe

**Architect (`architect.js`):**
- `AST[]`: array global con el árbol de bloques del protocolo
- `refresh()`: re-renderiza el canvas de bloques
- `doCompile()`: valida el AST y genera código Python
- `sendToReactor()`: llama a `/injectProtocol/` con el código compilado
- `_emitState()`: notifica al Nexus del estado actual del editor
- **Singleton Lock**: los bloques `init_temp`, `init_od`, `init_stir` deben ser los primeros 3. El resto se desbloquea solo cuando los 3 están presentes. **No relajar esta restricción.**

---

## Desarrollo local (sin BeagleBone)

```bash
# Instalar dependencias
pip install flask

# Ejecutar servidor mock (simula 3 reactores: M0, M1, M2)
python mock_server.py

# Abrir en navegador
http://localhost:5000
```

El `mock_server.py` simula todos los endpoints con datos biológicos realistas y fluctuantes.
M0 y M1 corren experimento, M2 está detenido.

---

## Despliegue en BeagleBone

```bash
# Conectar via PuTTY a 192.168.7.2, usuario root
# Copiar archivos modificados al BeagleBone (SCP o editor directo)

# Reiniciar servidor
pkill -f gunicorn && sleep 2 && bash cb.sh

# Verificar que corre
curl http://192.168.7.2:5000/getSysdata/
```

Cambios en `static/css/` y `static/js/` **no requieren reiniciar** — solo Ctrl+Shift+R en el navegador.
Cambios en `templates/` y `app.py` **sí requieren reiniciar** el servidor.

---

## Pendientes conocidos

- [ ] Configurar túnel nombrado de Cloudflare para el BeagleBone (actualmente usa quick tunnel con URL variable)
- [ ] Cacheo de respuestas Gemini para el mismo `protocolo.py` sin cambios
- [ ] Validación y sanitización del código recibido en `/injectProtocol/` antes de escribir al disco

---

## Errores frecuentes y soluciones

| Síntoma | Causa probable | Solución |
|---|---|---|
| Gráficas no cargan / datos en blanco | Error JS silencioso en `updateData()` por elemento HTML eliminado | Buscar `getElementById` nulo en consola del navegador |
| Flask no responde en `192.168.7.2:5000` | Gunicorn caído | `pkill -f gunicorn && sleep 2 && bash cb.sh` |
| Tema claro no funciona en Architect | Bug CSS `:root` sin cerrar antes de `[data-theme]` | Verificar que `:root{}` cierre antes del selector de tema |
| iframe Architect en blanco | Error JS en `architect.js` o endpoint `/architect` caído | Revisar consola del iframe (DevTools → frame selector) |
| Tema no se propaga al iframe | `postMessage` enviado antes de que el iframe termine de cargar | Esperar evento `load` del iframe antes de enviar |
| Gemini no responde | Billing inactivo o cuota agotada | Verificar Google Cloud Console |
