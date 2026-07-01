"""
Chi.Bio Nexus — Servidor de cámara WebRTC (Windows)
====================================================

Stack: FastAPI + aiortc + H.264 (con bitrate elevado).
- Señalización: WebSocket en /ws/signal (pasa por Cloudflare Tunnel)
- Video: P2P vía WebRTC (NO pasa por Cloudflare una vez negociado)
- Health: GET /health (consumido por el polling del Nexus)

Uso:
    pip install -r requirements-windows.txt
    python -m uvicorn camera.webrtc_server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import logging
import re
import time
import traceback
import uuid
from collections import deque
from fractions import Fraction
from typing import Any, Optional

import av
import cv2
import numpy as np
from aiortc import (
    MediaStreamTrack,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rtc_stream")

# aiortc 1.9.0 hardcodea MAX_BITRATE=3 Mbps en h264.py y 1.5 Mbps en vpx.py.
# El setter de target_bitrate clampea cualquier valor mayor, por lo que inyectar
# b=AS:/b=TIAS: en el SDP no ayuda. Hay que pisar las constantes de módulo
# ANTES de crear cualquier RTCPeerConnection.
try:
    from aiortc.codecs import h264 as _h264
    _h264.MIN_BITRATE     = 1_000_000
    _h264.DEFAULT_BITRATE = 6_000_000
    _h264.MAX_BITRATE     = 12_000_000
    log.info("aiortc H264 bitrate: %d/%d/%d (min/def/max)",
             _h264.MIN_BITRATE, _h264.DEFAULT_BITRATE, _h264.MAX_BITRATE)
except Exception as _e:
    log.warning("No se pudo elevar MAX_BITRATE H264 de aiortc: %s", _e)

try:
    from aiortc.codecs import vpx as _vpx
    _vpx.MIN_BITRATE     = 1_000_000
    _vpx.DEFAULT_BITRATE = 6_000_000
    _vpx.MAX_BITRATE     = 12_000_000
    log.info("aiortc VP8 bitrate: %d/%d/%d (min/def/max)",
             _vpx.MIN_BITRATE, _vpx.DEFAULT_BITRATE, _vpx.MAX_BITRATE)
except Exception as _e:
    log.warning("No se pudo elevar MAX_BITRATE VP8 de aiortc: %s", _e)

# ─────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────

CAMERA_INDEX   = 0       # índice de cámara (0 = default)
TARGET_FPS     = 30      # FPS deseados (ajustar según capacidad de la cámara)
FRAME_WIDTH    = 1280    # resolución ancho
FRAME_HEIGHT   = 720     # resolución alto (16:9 nativo, soportado por casi todas las webcams a 60fps)
BUFFER_SIZE    = 1       # ring buffer size: 1 = siempre el frame más fresco
MAX_PEERS      = 8       # máximo de clientes WebRTC simultáneos
CAPTURE_MAX_FAILURES = 50  # reintentos antes de reinicializar la cámara

# Orígenes permitidos para CORS. El polling /health del Nexus es cross-origin
# (Nexus en chibio.primbiolab.org → cámara en camera.primbiolab.org).
ALLOWED_ORIGINS = [
    "https://chibio.primbiolab.org",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]

# Servidores STUN/TURN para traversal de NAT
# Los de Google son gratuitos. Para producción seria, agrega un servidor TURN propio.
ICE_SERVERS = [
    RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
    RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
    RTCIceServer(urls=["stun:stun2.l.google.com:19302"]),
    # Para redes muy restrictivas (NAT simétrico, CGNAT), agregar TURN:
    # RTCIceServer(
    #     urls=["turn:tu-servidor-turn:3478"],
    #     username="usuario",
    #     credential="password"
    # ),
]

# ─────────────────────────────────────────────
# Ring buffer thread-safe para frames
# ─────────────────────────────────────────────

class FrameRingBuffer:
    """
    Almacena solo el frame más reciente. Elimina latencia acumulada:
    si el consumer va lento, siempre recibe el frame más fresco,
    nunca frames viejos en cola.
    """

    def __init__(self, maxsize: int = 1):
        self._buf: deque = deque(maxlen=maxsize)
        self._event = asyncio.Event()
        self._lock  = asyncio.Lock()

    async def put(self, frame):
        async with self._lock:
            self._buf.append(frame)
            self._event.set()

    async def get(self) -> Optional[Any]:
        await self._event.wait()
        async with self._lock:
            if self._buf:
                frame = self._buf[-1]   # siempre el más reciente
                self._event.clear()
                return frame
        return None

    def latest(self) -> Optional[Any]:
        """Acceso síncrono al frame más reciente sin bloquear. None si aún no hay frames."""
        return self._buf[-1] if self._buf else None


# ─────────────────────────────────────────────
# Captura de cámara en thread dedicado
# ─────────────────────────────────────────────

class CameraCapture:
    """
    Captura frames en un thread dedicado para no bloquear asyncio.
    Soporta encoding acelerado si hay GPU disponible.
    """

    def __init__(self, index: int = CAMERA_INDEX, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT, fps: int = TARGET_FPS):
        self.index  = index
        self.width  = width
        self.height = height
        self.fps    = fps
        self.buffer = FrameRingBuffer(maxsize=BUFFER_SIZE)
        self._cap   = None
        self._task  = None
        self._running = False

        # Stats
        self._frame_count = 0
        self._last_stats  = time.monotonic()
        self.actual_fps   = 0.0

    def _init_capture(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)  # Linux: V4L2 nativo
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)              # fallback genérico (Windows: MSMF/DSHOW auto)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS,          self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        actual_w   = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h   = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join(chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4))
        log.info(f"Cámara: {actual_w}x{actual_h} @ {actual_fps} FPS | fourcc={fourcc_str}")
        return cap

    async def _capture_loop(self):
        loop = asyncio.get_event_loop()
        self._cap = await loop.run_in_executor(None, self._init_capture)
        fail_count = 0

        while self._running:
            ret, frame = await loop.run_in_executor(None, self._cap.read)
            if not ret:
                fail_count += 1
                backoff = min(0.1 * fail_count, 2.0)
                log.warning(f"Frame vacío (intento {fail_count}), reintentando en {backoff:.1f}s...")
                if fail_count >= CAPTURE_MAX_FAILURES:
                    log.error("Cámara perdida. Reinicializando...")
                    await loop.run_in_executor(None, self._cap.release)
                    self._cap = await loop.run_in_executor(None, self._init_capture)
                    fail_count = 0
                    self.actual_fps = 0.0
                await asyncio.sleep(backoff)
                continue

            fail_count = 0
            await self.buffer.put(frame)
            self._frame_count += 1

            # Calcular FPS real cada 2 segundos
            now = time.monotonic()
            if now - self._last_stats >= 2.0:
                self.actual_fps = self._frame_count / (now - self._last_stats)
                log.info(f"Captura: {self.actual_fps:.1f} FPS")
                self._frame_count = 0
                self._last_stats  = now

    def start(self):
        self._running = True
        self._task = asyncio.ensure_future(self._capture_loop())
        log.info("Captura de cámara iniciada")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        if self._cap:
            self._cap.release()
        log.info("Captura de cámara detenida")


# ─────────────────────────────────────────────
# VideoStreamTrack para aiortc
# ─────────────────────────────────────────────

class CameraVideoTrack(MediaStreamTrack):
    """
    Track de video que toma frames del ring buffer y los envía vía WebRTC.
    Técnicas aplicadas:
      - Ring buffer tamaño 1: siempre el frame más fresco
      - Timestamp monotónico correcto para que el browser no re-bufferice
      - Codec H.264 con preset ultrafast (aiortc lo maneja automáticamente)
    """

    kind = "video"

    def __init__(self, camera: CameraCapture):
        super().__init__()
        self.camera = camera
        self._pts   = 0
        self._time_base = Fraction(1, 90000)  # 90 kHz clock estándar de RTP
        self._frame_duration = int(90000 / TARGET_FPS)
        self._last_frame = None

    async def recv(self):
        # Esperar el próximo frame del ring buffer
        bgr_frame = await self.camera.buffer.get()

        if bgr_frame is None:
            bgr_frame = self._last_frame or np.zeros(
                (FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8
            )
        else:
            self._last_frame = bgr_frame

        # BGR → YUV420p: formato nativo de H.264, evita doble conversión interna de aiortc
        yuv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2YUV_I420)
        video_frame = av.VideoFrame.from_ndarray(yuv, format="yuv420p")
        video_frame.pts      = self._pts
        video_frame.time_base = self._time_base
        self._pts += self._frame_duration

        return video_frame


# ─────────────────────────────────────────────
# Singleton de cámara (compartido entre conexiones)
# ─────────────────────────────────────────────

camera = CameraCapture(
    index=CAMERA_INDEX,
    width=FRAME_WIDTH,
    height=FRAME_HEIGHT,
    fps=TARGET_FPS,
)

# Registro de PeerConnections activos
peer_connections: dict[str, RTCPeerConnection] = {}


# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────

app = FastAPI(title="ChiBio Camera WebRTC", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    camera.start()
    log.info("Servidor listo")

@app.on_event("shutdown")
async def shutdown():
    camera.stop()
    for pc in list(peer_connections.values()):
        await pc.close()
    peer_connections.clear()


# ─────────────────────────────────────────────
# WebSocket de señalización (pasa por Cloudflare Tunnel)
# El video P2P nunca toca Cloudflare
# ─────────────────────────────────────────────

@app.websocket("/ws/signal")
async def signaling(ws: WebSocket):
    await ws.accept()
    client_id = str(uuid.uuid4())[:8]

    if len(peer_connections) >= MAX_PEERS:
        log.warning(f"[{client_id}] Rechazado: límite de {MAX_PEERS} peers alcanzado")
        await ws.send_json({"type": "error", "msg": "Máximo de conexiones simultáneas alcanzado"})
        await ws.close()
        return

    log.info(f"[{client_id}] Nuevo cliente conectado para señalización")

    config = RTCConfiguration(iceServers=ICE_SERVERS)
    pc = RTCPeerConnection(configuration=config)
    peer_connections[client_id] = pc

    # Agregar track de video al peer connection
    video_track = CameraVideoTrack(camera)
    pc.addTrack(video_track)

    @pc.on("connectionstatechange")
    async def on_state_change():
        state = pc.connectionState
        log.info(f"[{client_id}] Estado de conexión: {state}")
        if state in ("failed", "closed", "disconnected"):
            await pc.close()
            peer_connections.pop(client_id, None)

    @pc.on("iceconnectionstatechange")
    async def on_ice_change():
        log.info(f"[{client_id}] ICE: {pc.iceConnectionState}")

    try:
        async for raw in ws.iter_text():
            msg = json.loads(raw)
            kind = msg.get("type")

            # ── Paso 1: cliente envía SDP offer ──
            if kind == "offer":
                sdp = RTCSessionDescription(sdp=msg["sdp"], type="offer")
                await pc.setRemoteDescription(sdp)

                answer = await pc.createAnswer()
                # Insertar b=AS y b=TIAS después de c=IN en la sección de video
                # (b= debe ir después de c= según RFC 4566)
                sdp_patched, n_matches = re.subn(
                    r'(m=video[\s\S]*?)(c=IN[^\r\n]+\r\n)',
                    r'\1\2b=AS:8000\r\nb=TIAS:8000000\r\n',
                    answer.sdp,
                )
                if n_matches == 0:
                    log.warning(f"[{client_id}] SDP bitrate patch no aplicado (formato inesperado)")
                    sdp_patched = answer.sdp
                await pc.setLocalDescription(RTCSessionDescription(sdp=sdp_patched, type='answer'))

                await ws.send_json({
                    "type": "answer",
                    "sdp":  pc.localDescription.sdp,
                })
                log.info(f"[{client_id}] SDP answer enviado")

            # ── Paso 2: cliente envía ICE candidates ──
            elif kind == "ice":
                candidate = msg.get("candidate")
                if candidate:
                    from aiortc.sdp import candidate_from_sdp
                    try:
                        cand = candidate_from_sdp(candidate["candidate"].split(":", 1)[1])
                        cand.sdpMid        = candidate.get("sdpMid")
                        cand.sdpMLineIndex = candidate.get("sdpMLineIndex")
                        await pc.addIceCandidate(cand)
                    except Exception as e:
                        log.warning(f"[{client_id}] ICE candidate inválido: {e}")

            # ── Stats: cliente pide info ──
            elif kind == "stats":
                await ws.send_json({
                    "type": "stats",
                    "fps":  round(camera.actual_fps, 1),
                    "peers": len(peer_connections),
                })

    except WebSocketDisconnect:
        log.info(f"[{client_id}] Desconectado")
    except Exception as e:
        log.error(f"[{client_id}] Error: {e}\n{traceback.format_exc()}")
    finally:
        await pc.close()
        peer_connections.pop(client_id, None)
        log.info(f"[{client_id}] Limpieza completada")


# ─────────────────────────────────────────────
# Health endpoint (consumido por el polling del Nexus)
# ─────────────────────────────────────────────

_PREVIEW_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Chi.Bio — Cámara</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0b0e14; display: flex; flex-direction: column; align-items: center;
         justify-content: center; min-height: 100vh; font-family: 'Segoe UI', sans-serif; color: #e2ecf8; gap: 14px; }
  video { width: 100%; max-width: 1280px; border-radius: 12px; background: #10141c; display: block; }
  #status { font-size: 12px; color: #6080a0; font-family: Consolas, monospace; }
  #status.ok { color: #00d68f; }
  #status.err { color: #ff5c6c; }
</style>
</head>
<body>
<video id="v" autoplay playsinline muted></video>
<div id="status">Conectando...</div>
<script>
const v = document.getElementById('v');
const s = document.getElementById('status');

async function connect() {
  s.className = ''; s.textContent = 'Conectando...';
  const pc = new RTCPeerConnection({ iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ]});
  pc.ontrack = e => { if (e.streams[0]) v.srcObject = e.streams[0]; };
  pc.oniceconnectionstatechange = () => {
    const st = pc.iceConnectionState;
    if (st === 'connected' || st === 'completed') { s.className = 'ok'; s.textContent = 'Conectado — WebRTC 30 FPS'; }
    else if (st === 'failed') { s.className = 'err'; s.textContent = 'Fallo ICE — reintentando...'; pc.close(); setTimeout(connect, 2000); }
    else { s.className = ''; s.textContent = 'ICE: ' + st; }
  };
  const ws = new WebSocket('ws://127.0.0.1:8000/ws/signal');
  ws.onerror = () => { s.className = 'err'; s.textContent = 'Sin conexión con el servidor de cámara. ¿Está iniciado?'; };
  ws.onopen = async () => {
    const offer = await pc.createOffer({ offerToReceiveVideo: true });
    await pc.setLocalDescription(offer);
    ws.send(JSON.stringify({ type: 'offer', sdp: offer.sdp }));
    s.textContent = 'Negociando...';
  };
  ws.onmessage = async e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'answer') await pc.setRemoteDescription(new RTCSessionDescription(msg));
    else if (msg.type === 'ice' && msg.candidate) await pc.addIceCandidate(msg.candidate);
    else if (msg.type === 'error') { s.className = 'err'; s.textContent = 'Error: ' + msg.msg; }
  };
  pc.onicecandidate = e => { if (e.candidate) ws.send(JSON.stringify({ type: 'ice', candidate: e.candidate })); };
}
connect();
</script>
</body>
</html>"""


@app.get("/preview", response_class=HTMLResponse)
async def preview():
    """Visor WebRTC standalone — no requiere el Nexus ni la BBB."""
    return HTMLResponse(content=_PREVIEW_HTML)


@app.get("/frame")
async def get_frame():
    """Último frame capturado como JPEG. Útil para previews sin WebRTC."""
    frame = camera.buffer.latest()
    if frame is None:
        return Response(status_code=503)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not ok:
        return Response(status_code=500)
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.get("/health")
async def health():
    fps = round(camera.actual_fps, 1)
    if fps == 0.0:
        status = "down"
    elif fps < TARGET_FPS * 0.5:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "fps":    fps,
        "peers":  len(peer_connections),
    }


# ─────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        # SSL local deshabilitado: Cloudflare Tunnel maneja TLS externamente
        # ssl_keyfile="certs/key.pem",
        # ssl_certfile="certs/cert.pem",
        log_level="info",
        workers=1,   # 1 worker: la cámara es un recurso compartido singleton
    )
