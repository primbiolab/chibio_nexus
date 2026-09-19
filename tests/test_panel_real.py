"""
Panel Windows (lanzador_real.py): funciones puras y lógica sin ventana (self simulado con SimpleNamespace).

No abre la GUI, no ejecuta .ps1, no toca servicios, red ni firewall, y NO lee el config_pc.py real
(usa archivos sintéticos en tmp_path). Los `xfail(strict=True)` documentan bugs abiertos
(docs/historial/auditoria_2026-09-18.md, Fase D); se validan con el parche aplicado:
    python -m pytest tests/test_panel_real.py --runxfail
"""
import http.server
import os
import re
import threading
import types

import pytest

pytest.importorskip('customtkinter')
pytest.importorskip('PIL')

import lanzador_real as lr  # noqa: E402  (importarlo no abre ventanas: la GUI solo arranca en __main__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Server:
    """HTTP local: cada ruta se define con (status, cabeceras, cuerpo, retraso)."""
    def __init__(self, routes):
        seen = self.seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, dict(self.headers)))
                status, headers, body, delay = routes.get(self.path, (404, {}, b'', 0))
                if delay:
                    threading.Event().wait(delay)
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    made = []

    def make(routes):
        s = _Server(routes)
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


# ── _http_check: falla en cerrado ────────────────────────────

def test_http_check_200_es_ok(server):
    s = server({'/': (200, {}, b'ok', 0)})
    assert lr._http_check(s.url + '/') is True


@pytest.mark.parametrize('status', [401, 403, 404, 500, 503])
def test_http_check_error_http_es_falla(server, status):
    s = server({'/': (status, {}, b'', 0)})
    assert lr._http_check(s.url + '/') is False


def test_http_check_login_de_access_no_es_ok(server):
    """Sin token válido Access redirige a su login (que devuelve 200): debe contar como FALLA."""
    s = server({'/': (302, {'Location': '/cdn-cgi/access/login/x.cloudflareaccess.com'}, b'', 0),
                '/cdn-cgi/access/login/x.cloudflareaccess.com': (200, {}, b'login', 0)})
    assert lr._http_check(s.url + '/') is False


def test_http_check_sin_servidor_o_con_timeout_es_falla(server):
    s = server({'/lento': (200, {}, b'ok', 1.5)})
    assert lr._http_check(s.url + '/lento', timeout=0.4) is False
    s.close()
    assert lr._http_check(s.url + '/', timeout=0.5) is False


def test_http_check_envia_user_agent_y_cabeceras_de_access(server):
    s = server({'/': (200, {}, b'ok', 0)})
    lr._http_check(s.url + '/', access_headers={'CF-Access-Client-Id': 'id-de-prueba'})
    headers = {k.lower(): v for k, v in s.seen[0][1].items()}    # urllib normaliza mayúsculas
    assert headers['user-agent'] == 'Mozilla/5.0' and headers['cf-access-client-id'] == 'id-de-prueba'


# ── Diagnóstico ──────────────────────────────────────────────

def _panel(use_tunnel=False):
    return types.SimpleNamespace(
        _indices_lock=threading.Lock(), usb_index=1, _use_tunnel=use_tunnel,
        tunnel_url='https://tunel.invalido', _access_headers=None)


@pytest.fixture
def sin_sistema(monkeypatch):
    """Anula todo lo que toca red/servicios de Windows."""
    monkeypatch.setattr(lr, '_adapter_exists', lambda i: True)
    monkeypatch.setattr(lr, '_usb_ip_check', lambda i: True)
    monkeypatch.setattr(lr, '_tcp_check', lambda h, p, timeout=1.5: True)
    monkeypatch.setattr(lr, '_ping_check', lambda h, timeout_ms=1000: True)
    monkeypatch.setattr(lr, '_service_status', lambda n: 'Running')


def test_diagnostico_solo_lan_no_consulta_el_tunel(sin_sistema, server, monkeypatch):
    s = server({'/health': (200, {}, b'{"status":"ok","fps":30.0,"peers":0}', 0)})
    monkeypatch.setattr(lr, 'CAMERA_LOCAL_HEALTH', s.url + '/health')
    res = lr.PanelControl._calcular_diagnostico(_panel(use_tunnel=False))
    assert res['tunel_ok'] is None and res['camara_ok'] is True and len(res['lineas']) == 3


@pytest.mark.xfail(strict=True, reason='/health responde 200 con {"status":"down"} y _http_check solo mira <400: "Cámara local: OK" con la cámara caída')
def test_camara_down_no_cuenta_como_ok(sin_sistema, server, monkeypatch):
    s = server({'/health': (200, {}, b'{"status":"down","fps":0.0,"peers":0}', 0)})
    monkeypatch.setattr(lr, 'CAMERA_LOCAL_HEALTH', s.url + '/health')
    assert lr.PanelControl._calcular_diagnostico(_panel())['camara_ok'] is False


class _W:
    def itemconfig(self, *a, **k): pass
    def configure(self, *a, **k): pass


@pytest.mark.xfail(strict=True, reason='Diagnóstico completo en modo solo LAN: KeyError "tunel" en mostrar() (la fila no existe) → el informe nunca se muestra')
def test_diagnostico_completo_en_modo_solo_lan_muestra_el_informe():
    shown = []
    panel = types.SimpleNamespace(
        rows={k: (_W(), 1, _W()) for k in ('red', 'bbb', 'camara')},   # sin fila "tunel": _use_tunnel=False
        _use_tunnel=False, after=lambda ms, fn: fn(), _set_log=lambda t: None,
        _msg_info=lambda title, msg: shown.append(title),
        _calcular_diagnostico=lambda: {'lineas': ['1. ok'], 'red_ok': True, 'bbb_ok': True,
                                       'camara_ok': True, 'tunel_ok': None})
    panel._set_row = lambda key, ok: lr.PanelControl._set_row(panel, key, ok)
    lr.PanelControl._diagnostico_worker(panel)
    assert shown == ['Diagnóstico completo']


# ── config_pc.py (archivos sintéticos; nunca el real) ────────

CLAVES = ('TUNNEL_NAME', 'CHIBIO_HOSTNAME', 'CAMERA_HOSTNAME', 'CF_ACCESS_CLIENT_ID', 'CF_ACCESS_CLIENT_SECRET')


def test_leer_config_pc_lee_las_cinco_claves(tmp_path):
    (tmp_path / 'config_pc.py').write_text(
        'TUNNEL_NAME = "t"\nCHIBIO_HOSTNAME = "a.example.org"\nCAMERA_HOSTNAME = "c.example.org"\n'
        'CF_ACCESS_CLIENT_ID = "id"\nCF_ACCESS_CLIENT_SECRET = "sec"\n', encoding='utf-8')
    assert lr.PanelControl._leer_config_pc(None, str(tmp_path)) == {
        'TUNNEL_NAME': 't', 'CHIBIO_HOSTNAME': 'a.example.org', 'CAMERA_HOSTNAME': 'c.example.org',
        'CF_ACCESS_CLIENT_ID': 'id', 'CF_ACCESS_CLIENT_SECRET': 'sec'}


def test_leer_config_pc_ausente_o_corrupto_da_vacios_sin_excepcion(tmp_path):
    vacio = {k: '' for k in CLAVES}
    assert lr.PanelControl._leer_config_pc(None, str(tmp_path)) == vacio
    (tmp_path / 'config_pc.py').write_bytes(b'\xff\xfe\x00basura')
    assert lr.PanelControl._leer_config_pc(None, str(tmp_path)) == vacio


def _valores(**kw):
    v = {'TUNNEL_NAME': 'tun', 'CHIBIO_HOSTNAME': 'a.example.org', 'CAMERA_HOSTNAME': 'c.example.org',
         'CF_ACCESS_CLIENT_ID': 'id', 'CF_ACCESS_CLIENT_SECRET': 'sec'}
    v.update(kw)
    return v


@pytest.mark.xfail(strict=True, reason='guardar() escribe config_pc.py in situ (open "w"): un corte deja el archivo truncado; falta _escribir_config_pc atómica')
def test_escribir_config_pc_ida_y_vuelta(tmp_path):
    lr._escribir_config_pc(str(tmp_path), _valores())
    assert lr.PanelControl._leer_config_pc(None, str(tmp_path)) == _valores()
    compile((tmp_path / 'config_pc.py').read_text(encoding='utf-8'), 'config_pc.py', 'exec')  # es Python válido


@pytest.mark.xfail(strict=True, reason='escritura no atómica de config_pc.py')
def test_escribir_config_pc_es_atomica(tmp_path, monkeypatch):
    lr._escribir_config_pc(str(tmp_path), _valores())
    antes = (tmp_path / 'config_pc.py').read_bytes()

    def falla(*a, **k):
        raise OSError('disco lleno')
    monkeypatch.setattr(os, 'replace', falla)
    with pytest.raises(OSError):
        lr._escribir_config_pc(str(tmp_path), _valores(TUNNEL_NAME='otro'))
    assert (tmp_path / 'config_pc.py').read_bytes() == antes


@pytest.mark.xfail(strict=True, reason='valores con comillas/saltos de línea rompen config_pc.py (se interpolan en código Python)')
@pytest.mark.parametrize('malo', ['a"b', "a'b", 'a\\b', 'a\nb'])
def test_escribir_config_pc_rechaza_caracteres_que_rompen_el_archivo(tmp_path, malo):
    with pytest.raises(ValueError):
        lr._escribir_config_pc(str(tmp_path), _valores(CF_ACCESS_CLIENT_SECRET=malo))
    assert not (tmp_path / 'config_pc.py').exists()


# ── LOCAL_HOST congelado en el .exe ──────────────────────────

def test_local_host_es_la_bbb_real():
    """Un .exe congela LOCAL_HOST: si alguien lo deja en 127.0.0.1 (pruebas con el mock) y compila, el panel queda roto."""
    assert lr.LOCAL_HOST == '192.168.7.2'


@pytest.mark.xfail(strict=True, reason='compilar.ps1 compila sin validar LOCAL_HOST')
def test_compilar_valida_local_host():
    with open(os.path.join(ROOT, 'compilar.ps1'), encoding='utf-8-sig') as f:
        assert re.search(r'LOCAL_HOST', f.read())
