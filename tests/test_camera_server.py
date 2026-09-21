"""
Servidor de cámara (camera/webrtc_server.py) con cámara SIMULADA: HTTP y /ws/signal reales sobre 127.0.0.1
(uvicorn en un subproceso), más pruebas en proceso del ring buffer y del bucle de captura.

Cubren los bugs de la auditoría (docs/historial/auditoria_2026-09-18.md, Fase C), ya corregidos en webrtc_server.py.
Nunca se abre la webcam real ni se escucha fuera de 127.0.0.1. Requiere fastapi/aiortc/opencv/websockets.
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('aiortc')
cv2 = pytest.importorskip('cv2')
np = pytest.importorskip('numpy')
ws_client = pytest.importorskip('websockets.sync.client')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, 'tests', 'camera_fake_server.py')
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _get(port, path):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, path), timeout=5) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', ''), e.read()


def _start(mode):
    port = _free_port()
    proc = subprocess.Popen([sys.executable, FAKE, mode, str(port)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            _get(port, '/health')
            return proc, port
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError('el servidor de cámara no arrancó')


@pytest.fixture(scope='module')
def cam_none():
    proc, port = _start('none')
    yield port
    proc.kill()


@pytest.fixture(scope='module')
def cam_frames():
    proc, port = _start('frames')
    time.sleep(3.0)      # el FPS real se calcula cada 2 s
    yield port
    proc.kill()


def _ws(port, ip=None, origin=None):
    headers = {'cf-connecting-ip': ip} if ip else {}
    return ws_client.connect('ws://127.0.0.1:%d/ws/signal' % port, origin=origin,
                             additional_headers=headers, open_timeout=5)


def _rejected(sock):
    """True si el servidor contesta con {"type":"error"} y cierra."""
    try:
        return json.loads(sock.recv(timeout=2)).get('type') == 'error'
    except Exception:
        return False


# ── HTTP ─────────────────────────────────────────────────────

def test_health_sin_camara_es_200_con_status_down(cam_none):
    """Caracterización: /health responde 200 aun con la cámara caída; el consumidor debe leer el JSON."""
    status, _, body = _get(cam_none, '/health')
    assert status == 200 and json.loads(body)['status'] == 'down'


def test_frame_sin_camara_503(cam_none):
    assert _get(cam_none, '/frame')[0] == 503


def test_health_y_frame_con_camara(cam_frames):
    status, _, body = _get(cam_frames, '/health')
    data = json.loads(body)
    assert status == 200 and data['status'] == 'ok' and data['fps'] > 15
    status, ctype, body = _get(cam_frames, '/frame')
    assert status == 200 and ctype == 'image/jpeg' and body[:2] == b'\xff\xd8'


def test_preview_sirve_html(cam_none):
    status, ctype, body = _get(cam_none, '/preview')
    assert status == 200 and 'text/html' in ctype and b'/ws/signal' in body


# ── Señalización: origin y límites ───────────────────────────

def test_ws_origin_ajeno_rechazado(cam_none):
    with pytest.raises(Exception):
        _ws(cam_none, origin='https://evil.example').close()


def test_ws_origin_nexus_permitido(cam_none):
    _ws(cam_none, origin='https://chibio.primbiolab.org').close()


def test_ws_origin_de_preview_permitido(cam_none):
    _ws(cam_none, origin='http://127.0.0.1:8000').close()


def test_ws_limite_por_ip(cam_none):
    socks = [_ws(cam_none, ip='9.9.9.9') for _ in range(2)]
    third = _ws(cam_none, ip='9.9.9.9')
    try:
        assert _rejected(third)
    finally:
        for s in socks + [third]:
            s.close()


def test_ws_limite_global_y_cabecera_falsificable(cam_none):
    """Caracterización: la IP sale de `cf-connecting-ip`; quien llegue directo al puerto la falsifica y esquiva
    el límite por IP (hasta MAX_PEERS=8). Por eso la cámara solo debe escuchar en 127.0.0.1 (cloudflared local)."""
    socks = [_ws(cam_none, ip='10.0.0.%d' % i) for i in range(8)]
    ninth = _ws(cam_none, ip='10.0.0.99')
    try:
        assert _rejected(ninth)
    finally:
        for s in socks + [ninth]:
            s.close()
        time.sleep(0.5)


# ── Enlace de red: nunca 0.0.0.0 ─────────────────────────────

@pytest.mark.parametrize('rel', ['scripts/pc/instalar_servicios.ps1', 'camera/webrtc_server.py'])
def test_camara_no_escucha_en_todas_las_interfaces(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        assert '0.0.0.0' not in f.read()


# ── Módulo en proceso: ring buffer y captura ─────────────────

def _module():
    from camera import webrtc_server
    return webrtc_server


def test_ring_buffer_reparte_todos_los_frames_entre_espectadores():
    """Hipótesis del informe (fps/N con N espectadores): refutada; cada consumidor recibe ~todos los frames."""
    wm = _module()

    async def scenario(n_consumers=4, frames=60):
        buf = wm.FrameRingBuffer(maxsize=1)
        got = [0] * n_consumers

        async def consumer(i):
            while True:
                await buf.get()
                got[i] += 1

        tasks = [asyncio.ensure_future(consumer(i)) for i in range(n_consumers)]
        await asyncio.sleep(0)
        for k in range(frames):
            await buf.put(k)
            await asyncio.sleep(1 / 30)
        await asyncio.sleep(0.1)
        for t in tasks:
            t.cancel()
        return got

    got = asyncio.run(scenario())
    assert min(got) >= 0.9 * 60, got


class _Cap:
    """cv2.VideoCapture falso: `good` frames a ~30 fps y después `after`: 'raise' o 'empty'."""
    def __init__(self, good, after):
        self.n, self.good, self.after = 0, good, after

    def isOpened(self): return True
    def set(self, *a): return True
    def get(self, prop): return 30.0
    def release(self): pass

    def read(self):
        time.sleep(1 / 30)
        self.n += 1
        if self.n <= self.good:
            return True, np.zeros((72, 128, 3), dtype=np.uint8)
        if self.after == 'raise':
            raise RuntimeError('camera lost')
        return False, None


def test_captura_sobrevive_a_una_excepcion_de_read(monkeypatch):
    wm = _module()
    monkeypatch.setattr(wm.cv2, 'VideoCapture', lambda *a, **k: _Cap(good=5, after='raise'))

    async def scenario():
        cam = wm.CameraCapture()
        cam.start()
        await asyncio.sleep(1.0)
        done = cam._task.done()
        cam.stop()
        return done

    assert asyncio.run(scenario()) is False


def test_health_deja_de_decir_ok_si_no_llegan_frames(monkeypatch):
    wm = _module()
    monkeypatch.setattr(wm.cv2, 'VideoCapture', lambda *a, **k: _Cap(good=78, after='empty'))

    async def scenario():
        cam = wm.CameraCapture()
        monkeypatch.setattr(wm, 'camera', cam)
        cam.start()
        await asyncio.sleep(2.4)                     # ya calculó ~30 fps
        before = (await wm.health())['status']
        await asyncio.sleep(4.0)                     # llevan ~4 s sin frames
        after = (await wm.health())['status']
        cam.stop()
        return before, after

    before, after = asyncio.run(scenario())
    assert before == 'ok' and after != 'ok'


def test_ice_descarta_interfaces_sin_ruta_pero_nunca_todas():
    # aioice espera 5 s por cada interfaz que acepta bind y no tiene ruta (host-only de VirtualBox, VPN caída):
    # cada espectador tardaba +5 s en recibir el answer. Se descartan; si ninguna pasa, se conservan todas.
    ws = _module()
    ok = {'172.16.24.111', '192.168.7.1'}
    addrs = ['169.254.155.226', '192.168.7.1', '192.168.56.1', '172.16.24.111']
    assert ws._filter_reachable_hosts(addrs, lambda a: a in ok) == ['192.168.7.1', '172.16.24.111']
    assert ws._filter_reachable_hosts(addrs, lambda a: False) == addrs


def test_ice_get_host_addresses_de_aioice_esta_filtrado():
    from aioice import ice
    _module()
    assert ice.get_host_addresses.__module__ == _module().__name__
