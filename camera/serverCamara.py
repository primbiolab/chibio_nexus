"""
Chi.Bio Generic Camera Server
Stream de video MJPEG para cualquier cámara detectada
"""

import cv2
import numpy as np
import time
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permite que el Nexus consuma el stream desde otro dominio o puerto

# ── Configuración Genérica ──────────────────────────────────
CAMERA_INDEX = 0       # 0 = primera cámara (webcam integrada o USB)
JPEG_QUALITY = 80      # Calidad de compresión (0-100)

# ── Parámetros de imagen ajustables en tiempo real ──────────
BRIGHTNESS   = 1.0     # rango [0.5, 2.0] — multiplicador de valor (HSV)
CONTRAST     = 1.0     # rango [0.5, 2.0] — escala alrededor de gris medio (128)
SATURATION   = 1.0     # rango [0.5, 2.0] — multiplicador de saturación (HSV)

# Flag de estado de cámara; lo actualiza generate_frames()
# Thread-safety: estas variables son escritas por el thread del generador y leídas
# por threads de request Flask. El GIL de CPython garantiza atomicidad en lecturas/
# escrituras de referencias (scalars y asignaciones de objeto). _last_frame usa
# .copy() antes de asignar, lo que hace la sustitución de referencia atómica.
_cam_online  = False
_last_frame  = None   # último frame capturado (antes de filtros), para /capture
_fps_data    = {'fps': 0.0, 'count': 0, 'window': 0.0}

# ── Helpers ────────────────────────────────────────────────
def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, float(value)))

def apply_filters(frame):
    """Aplica brillo, contraste y saturación al frame BGR."""
    # Early-return cuando todo está en neutro — sin coste de procesamiento
    if BRIGHTNESS == 1.0 and CONTRAST == 1.0 and SATURATION == 1.0:
        return frame

    # Brillo y saturación en espacio HSV (preserva tonos)
    if BRIGHTNESS != 1.0 or SATURATION != 1.0:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
        if SATURATION != 1.0:
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * SATURATION, 0, 255)
        if BRIGHTNESS != 1.0:
            hsv[:, :, 2] = np.clip(hsv[:, :, 2] * BRIGHTNESS, 0, 255)
        frame = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # Contraste escalado alrededor de gris medio (128) — no afecta brillo medio
    if CONTRAST != 1.0:
        f = frame.astype(np.float32)
        frame = np.clip(CONTRAST * (f - 128.0) + 128.0, 0, 255).astype(np.uint8)

    return frame

# ── Generador de frames ────────────────────────────────────
def generate_frames():
    global _cam_online, _last_frame, _fps_data
    _fps_data = {'fps': 0.0, 'count': 0, 'window': time.time()}
    cap = cv2.VideoCapture(CAMERA_INDEX)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    if not cap.isOpened():
        print(f"[ERROR] No se pudo acceder a la cámara con índice {CAMERA_INDEX}.")
        _cam_online = False
        return

    _cam_online = True
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[OK] Streaming activo: {w}x{h}")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Cachear frame crudo y actualizar FPS
        _last_frame = frame.copy()
        _fps_data['count'] += 1
        now = time.time()
        elapsed = now - _fps_data['window']
        if elapsed >= 1.0:
            _fps_data['fps'] = round(_fps_data['count'] / elapsed, 1)
            _fps_data['count'] = 0
            _fps_data['window'] = now

        frame = apply_filters(frame)

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, int(JPEG_QUALITY)])
        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
        )

    _cam_online = False
    cap.release()

# ── Endpoints ──────────────────────────────────────────────
@app.route('/video_feed')
def video_feed():
    """Endpoint principal para el src del iframe o img"""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/status')
def status():
    """Consulta de estado — usa el flag interno, no abre una captura nueva"""
    return jsonify({
        'camera_status': 'online' if _cam_online else 'offline',
        'source_index': CAMERA_INDEX
    })

@app.route('/settings', methods=['GET'])
def get_settings():
    """Retorna estado actual de todos los controles de imagen"""
    return jsonify({
        'brightness':    BRIGHTNESS,
        'contrast':      CONTRAST,
        'saturation':    SATURATION,
        'jpeg_quality':  JPEG_QUALITY,
        'fps':           _fps_data['fps'],
        'camera_status': 'online' if _cam_online else 'offline'
    })

@app.route('/settings', methods=['POST'])
def update_settings():
    """Actualiza parámetros de imagen en tiempo real (sin reiniciar el stream)"""
    global BRIGHTNESS, CONTRAST, SATURATION, JPEG_QUALITY
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body requerido'}), 400

    if 'brightness'   in data: BRIGHTNESS   = clamp(data['brightness'],   0.5,  2.0)
    if 'contrast'     in data: CONTRAST     = clamp(data['contrast'],     0.5,  2.0)
    if 'saturation'   in data: SATURATION   = clamp(data['saturation'],   0.5,  2.0)
    if 'jpeg_quality' in data: JPEG_QUALITY = int(clamp(data['jpeg_quality'], 30, 100))

    return jsonify({
        'status':       'ok',
        'brightness':   BRIGHTNESS,
        'contrast':     CONTRAST,
        'saturation':   SATURATION,
        'jpeg_quality': JPEG_QUALITY
    })

@app.route('/capture')
def capture():
    """Captura y descarga el último frame procesado con los filtros activos"""
    if _last_frame is None:
        return jsonify({'error': 'No hay frame disponible — inicia el stream primero'}), 503
    frame = apply_filters(_last_frame)
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, int(JPEG_QUALITY)])
    ts = time.strftime('%Y%m%d_%H%M%S')
    return Response(
        buffer.tobytes(),
        mimetype='image/jpeg',
        headers={'Content-Disposition': f'attachment; filename=chibio_{ts}.jpg'}
    )

@app.route('/')
def index():
    """Página de visualización directa"""
    return '''
    <html><body style="margin:0;background:#000;display:flex;align-items:center;justify-content:center;">
    <img src="/video_feed" style="max-width:100%;max-height:100vh;object-fit:contain">
    </body></html>
    '''

# ── Arranque ───────────────────────────────────────────────
if __name__ == '__main__':
    print(f"Iniciando servidor de cámara genérico en puerto 5001...")
    app.run(host='0.0.0.0', port=5001, threaded=True)
